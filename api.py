from flask import Flask, request, jsonify, send_from_directory
import aiohttp, asyncio
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs
from collections import Counter

app = Flask(__name__)

@app.route("/")
def root():
    return send_from_directory('.', 'index.html')

@app.route("/analyser", methods=["POST"])
def analyser():
    data = request.json
    input_text = data.get("url", "").strip()

    # Extraire les pseudos depuis un lien OP.GG MultiSearch ou texte brut
    summoners = extract_summoners(input_text)
    if not summoners or len(summoners) < 1:
        return jsonify({"error": "Aucun pseudo valide détecté."})

    summoners = summoners[:5]  # On prend seulement les 5 premiers
    result = asyncio.run(collect_data(summoners))
    return jsonify(result)

def extract_summoners(text):
    summoners = []

    if "op.gg" in text:
        # Extraire paramètres d’un lien OP.GG
        parsed_url = urlparse(text)
        query = parse_qs(parsed_url.query)
        summoner_param = query.get("summoners", [""])[0]
        decoded = unquote(summoner_param)
        raw_names = decoded.replace("+", "").split(",")
        summoners = [s.strip() for s in raw_names if s.strip()]
    else:
        # Entrée manuelle brute : Joueur1#EUW, Joueur2#EUW
        raw_names = text.replace("+", "").split(",")
        summoners = [s.strip() for s in raw_names if s.strip()]

    return summoners

async def collect_data(summoner_names):
    order = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]
    players = []

    for summoner in summoner_names:
        encoded_name = summoner.replace('#', '%23').replace(' ', '%20')
        url = f"https://www.op.gg/summoners/euw/{encoded_name}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        champs = soup.select("div.most-champions > ul > li")[:5]
        cdata, roles = [], Counter()

        for champ in champs:
            name_tag = champ.select_one(".name")
            games_tag = champ.select_one(".count")
            winrate_tag = champ.select_one(".win")

            if not name_tag or not games_tag or not winrate_tag:
                continue

            name = name_tag.text.strip()
            games = int(games_tag.text.strip().split()[0])
            winrate = int(winrate_tag.text.strip().replace("%", ""))
            role = "UNKNOWN"

            role_tag = champ.select_one(".position")
            if role_tag:
                role = role_tag.text.strip().upper()
                roles[role] += 1

            cdata.append({
                "name": name,
                "games": games,
                "winrate": winrate
            })

        if not cdata:
            continue

        main_role = roles.most_common(1)[0][0] if roles else "UNKNOWN"
        top3 = sorted(cdata, key=lambda x: (x["games"], x["winrate"]), reverse=True)[:3]

        players.append({
            "summoner": summoner,
            "role": main_role,
            "champions": top3
        })

    players = sorted(players, key=lambda p: order.index(p["role"]) if p["role"] in order else 99)
    return {"players": players}

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
