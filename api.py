import os
import aiohttp
import asyncio
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

# Charger les variables d'environnement (.env)
load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
REGION = "europe"    # Pour EUW / EUNE
PLATFORM = "euw1"    # EUW platform ID

app = Flask(__name__)

# Route racine → sert index.html
@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

# Fonction utilitaire pour requêtes API Riot
async def fetch_json(session, url, headers):
    async with session.get(url, headers=headers) as response:
        return await response.json()

# Obtenir les infos du joueur par nom
async def get_summoner_data(summoner_name, session, headers):
    url = f"https://{PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{summoner_name}"
    return await fetch_json(session, url, headers)

# Récupérer les matchs par PUUID
async def get_match_history(puuid, session, headers):
    match_ids_url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=10"
    match_ids = await fetch_json(session, match_ids_url, headers)
    
    match_data = []
    for match_id in match_ids:
        url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        data = await fetch_json(session, url, headers)
        match_data.append(data)
    return match_data

# Endpoint principal
@app.route("/analyser", methods=["POST"])
def analyser():
    data = request.json
    names = data.get("summoners", [])
    if not names or not isinstance(names, list):
        return jsonify({"error": "Merci de fournir une liste de pseudos."}), 400

    result = asyncio.run(process_summoners(names))
    return jsonify(result)

# Traitement de chaque joueur
async def process_summoners(summoner_names):
    headers = {"X-Riot-Token": RIOT_API_KEY}
    async with aiohttp.ClientSession() as session:
        team_data = []

        for name in summoner_names[:5]:  # max 5 joueurs
            summoner = await get_summoner_data(name, session, headers)
            puuid = summoner.get("puuid")
            if not puuid:
                continue

            matches = await get_match_history(puuid, session, headers)
            champ_stats = {}

            for match in matches:
try:
    participants = match["info"]["participants"]
    player_data = next(p for p in participants if p["puuid"] == puuid)
    champ_name = player_data["championName"]
    win = player_data["win"]
    champ_stats.setdefault(champ_name, {"games": 0, "wins": 0})
    champ_stats[champ_name]["games"] += 1
    champ_stats[champ_name]["wins"] += int(win)
except Exception as e:
    print(f"[Erreur analyse match] {e}")
    print(f"[Match brut] {match}")
    continue



            stats_list = []
            for champ, stats in champ_stats.items():
                winrate = int((stats["wins"] / stats["games"]) * 100)
                stats_list.append({
                    "champion": champ,
                    "games": stats["games"],
                    "winrate": winrate
                })

            stats_list = sorted(stats_list, key=lambda x: (x["games"], x["winrate"]), reverse=True)[:3]

            team_data.append({
                "summoner": name,
                "champions": stats_list
            })

        return {"players": team_data}

# Lancer le serveur (dev ou Railway)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
