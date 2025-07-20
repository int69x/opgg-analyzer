import os
import aiohttp
import asyncio
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
if not RIOT_API_KEY:
    print("⚠️ RIOT_API_KEY non trouvé. Assure-toi de l'avoir dans Railway > Variables.")

REGION = "europe"
PLATFORM = "euw1"

app = Flask(__name__)

@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

@app.route("/analyser", methods=["POST"])
def analyser():
    data = request.json or {}
    names = data.get("summoners", [])
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]

    if not names:
        return jsonify({"error": "Aucun pseudo fourni."}), 400

    names = names[:5]
    result = asyncio.run(process_summoners(names))
    print("[✅ Résultat JSON final]", result)
    return jsonify(result)

async def fetch_json(session, url, headers):
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            text = await resp.text()
            print(f"[HTTP {resp.status}] {url} → {text}")
        try:
            return await resp.json()
        except:
            return {}

async def get_summoner(name, session):
    url = f"https://{PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{name}"
    return await fetch_json(session, url, {"X-Riot-Token": RIOT_API_KEY})

async def get_match_ids(puuid, session):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=20"
    return await fetch_json(session, url, {"X-Riot-Token": RIOT_API_KEY}) or []

async def get_match(match_id, session):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return await fetch_json(session, url, {"X-Riot-Token": RIOT_API_KEY})

async def process_summoners(names):
    async with aiohttp.ClientSession() as session:
        players = []
        for nm in names:
            print(f"[▶ Analyse de] {nm}")
            summ = await get_summoner(nm, session)
            puuid = summ.get("puuid")
            if not puuid:
                print(f"[❌ Pas de PUUID pour] {nm}")
                players.append({"summoner": nm, "champions": [], "error": "Introuvable"})
                continue

            ids = await get_match_ids(puuid, session)
            champ_stats = {}
            for mid in ids:
                m = await get_match(mid, session)
                participants = m.get("info", {}).get("participants", [])
                me = next((p for p in participants if p.get("puuid") == puuid), None)
                if not me:
                    continue
                champ = me.get("championName")
                win = me.get("win", False)
                st = champ_stats.setdefault(champ, {"games": 0, "wins": 0})
                st["games"] += 1
                st["wins"] += int(win)

            stats = [{"champion": c, "games": v["games"], "winrate": int((v["wins"] / v["games"]) * 100)} for c, v in champ_stats.items()]
            stats.sort(key=lambda x: (x["games"], x["winrate"]), reverse=True)
            players.append({"summoner": nm, "champions": stats[:3]})

        return {"players": players}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
