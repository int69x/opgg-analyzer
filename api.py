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
    summoners = extract_summoners(input_text)
    if not summoners or len(summoners) < 1:
        return jsonify({"error": "Aucun pseudo valide détecté."})

    summoners = summoners[:5]
    result = asyncio.run(collect_data(summoners))
    return jsonify(result)

def extract_summoners(text):
    summoners = []
    if "op.gg" in text:
        parsed_url = urlparse(text)
        query = parse_qs(parsed_url.query)
        summoner_param = query.get("summoners", [""])[0]
        decoded = unquote(summoner_param)
        raw_names = decoded.replace("+", "").split(",")
        summoners = [s.strip() for s in raw_names if s.strip()]
    else:
        raw_names = text.replace("+", "").split(",")
        summoners = [s.strip() for s in raw_names if s.strip()]
    return summoners

async def collect_data(summoner_names):
    order = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]
    players = []

    for summoner in summoner_names:
        encoded = summoner.replace("#", "%23").replace(" ", "%20")
        url = f"https://www.op.gg/summoners/euw/{encoded}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        champ_rows = soup.select(".css-1wvykus")  # nouveau sélecteur 2025
        if not champ_rows:
            continue

        cdata, roles = [], Counter()

        for champ in champ_rows[:5]:
            name_tag = champ.select_one(".champion-name")
            games_tag = champ.select_one(".played")
            win_tag = champ.select_one(".winratio")
            role_tag = champ.select_one(".position")

            if name_tag and games_tag and win_tag:
                name = name_tag.text.strip()
                games = int(games_tag.text.strip().split()[0])
                winrate = int(win_tag.text.strip().replace("%", ""))
                role = role_tag.text.strip().upper() if role_tag else "UNKNOWN"
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
