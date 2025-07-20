import os
import aiohttp
import asyncio
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

# Charge les variables (.env local / Variables Railway)
load_dotenv()
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
if not RIOT_API_KEY:
    print("⚠️  RIOT_API_KEY manquante. Ajoute-la dans Railway > Variables.")

# Config serveurs Riot
REGION = "europe"   # 'americas', 'asia', etc. Selon shard Match-V5
PLATFORM = "euw1"   # 'euw1', 'na1', etc. Pour Summoner-V4

app = Flask(__name__)

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    """Servez la page web."""
    return send_from_directory('.', 'index.html')

@app.route("/health")
def health():
    return {"ok": True}

@app.route("/analyser", methods=["POST"])
def analyser():
    """Analyse une liste (<=5) de pseudos Riot et renvoie leurs champions récents."""
    data = request.json or {}
    names = data.get("summoners", [])
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]
    if not names or not isinstance(names, list):
        return jsonify({"error": "Merci de fournir une liste de pseudos."}), 400

    # Limite à 5
    names = names[:5]

    try:
        result = asyncio.run(process_summoners(names))
    except Exception as e:
        print(f"[❌ ERREUR analyser()] {e}")
        return jsonify({"error": "Erreur interne serveur."}), 500

    return jsonify(result)

# -----------------------------------------------------------------------------
# Riot API helpers
# -----------------------------------------------------------------------------
async def fetch_json(session, url, headers):
    async with session.get(url, headers=headers) as resp:
        # Log en cas d'erreur HTTP
        if resp.status != 200:
            txt = await resp.text()
            print(f"[HTTP {resp.status}] {url} -> {txt}")
        try:
            return await resp.json()
        except Exception as e:
            print(f"[❌ JSON parse] {url} -> {e}")
            return {}

async def get_summoner_data(summoner_name, session, headers):
    url = f"https://{PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{summoner_name}"
    return await fetch_json(session, url, headers)

async def get_match_ids(puuid, session, headers, count=10):
    url = (
        f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/"
        f"{puuid}/ids?start=0&count={count}"
    )
    data = await fetch_json(session, url, headers)
    # Data peut être liste ou dict erreur
    return data if isinstance(data, list) else []

async def get_match(match_id, session, headers):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return await fetch_json(session, url, headers)

# -----------------------------------------------------------------------------
# Core processing
# -----------------------------------------------------------------------------
async def process_summoners(summoner_names):
    headers = {"X-Riot-Token": RIOT_API_KEY}
    team_data = []

    async with aiohttp.ClientSession() as session:
        for name in summoner_names:
            print(f"\n[▶] Analyse de {name}")

            # --- Summoner infos ---
            summoner = await get_summoner_data(name, session, headers)
            if not isinstance(summoner, dict) or "puuid" not in summoner:
                print(f"[❌] Impossible de récupérer {name}")
                team_data.append({
                    "summoner": name,
                    "error": "Introuvable ou API Riot indisponible.",
                    "champions": []
                })
                continue

            puuid = summoner["puuid"]

            # --- Match IDs ---
            match_ids = await get_match_ids(puuid, session, headers, count=20)
            if not match_ids:
                print(f"[⚠️] Aucun match récent pour {name}")
                team_data.append({
                    "summoner": name,
                    "error": "Aucune partie récente.",
                    "champions": []
                })
                continue

            # --- Récup matches et stats champ ---
            champ_stats = {}
            for match_id in match_ids:
                match = await get_match(match_id, session, headers)
                try:
                    participants = match["info"]["participants"]
                    player_data = next(p for p in participants if p["puuid"] == puuid)
                except Exception as e:
                    print(f"[Erreur analyse match {match_id}] {e}")
                    continue

                champ_name = player_data.get("championName", "UNKNOWN")
                win = bool(player_data.get("win", False))

                cs = champ_stats.setdefault(champ_name, {"games": 0, "wins": 0})
                cs["games"] += 1
                cs["wins"] += int(win)

            # --- Construire top 3 ---
            stats_list = []
            for champ, stats in champ_stats.items():
                winrate = int((stats["wins"] / stats["games"]) * 100) if stats["games"] else 0
                stats_list.append({
                    "champion": champ,
                    "games": stats["games"],
                    "winrate": winrate,
                })

            stats_list.sort(key=lambda x: (x["games"], x["winrate"]), reverse=True)
            stats_list = stats_list[:3]

            team_data.append({
                "summoner": name,
                "champions": stats_list
            })

    result = {"players": team_data}
    print("\n[✅ Résultat JSON final]")
    print(result)
    return result

# -----------------------------------------------------------------------------
# Run (local / Railway)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Flask debug en local si besoin :
    debug_mode = bool(int(os.getenv("FLASK_DEBUG", "0")))
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)), debug=debug_mode)
