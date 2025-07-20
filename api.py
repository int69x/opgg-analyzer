from flask import Flask, request, jsonify, send_from_directory
import aiohttp, asyncio
from bs4 import BeautifulSoup
from collections import Counter

app = Flask(__name__)

@app.route("/")
def root():
    return send_from_directory('.', 'index.html')

@app.route("/analyser", methods=["POST"])
def analyser():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL manquante"}), 400
    result = asyncio.run(collect_data(url))
    return jsonify(result)

async def collect_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    summoners = soup.find_all("a", class_="summoner-name")
    names = [s.text.strip() for s in summoners]
    if len(names) != 5:
        return {"error": f"{len(names)} détectés, 5 attendus"}
    order = ["TOP","JUNGLE","MID","ADC","SUPPORT"]
    players = []
    for summoner in names:
        async with aiohttp.ClientSession() as session:
            urlp = f"https://www.op.gg/summoners/euw/{summoner.replace(' ', '%20')}"
            async with session.get(urlp) as resp:
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        champs = soup.select("div.css-12f1g4f")[:5]
        cdata, roles = [], Counter()
        for c in champs:
            n = c.select_one(".champion-name")
            g = c.select_one(".played")
            w = c.select_one(".winratio")
            p = c.select_one(".position")
            if n and g and w and p:
                name = n.text.strip()
                games = int(g.text.split()[0])
                win = int(w.text.replace("%",""))
                role = p.text.strip().upper()
                roles[role] += 1
                cdata.append({"name": name, "games": games, "winrate": win})
        main = roles.most_common(1)[0][0] if roles else "UNK"
        top3 = sorted(cdata, key=lambda x: (x["games"], x["winrate"]), reverse=True)[:3]
        players.append({"summoner": summoner, "role": main, "champions": top3})
    players = sorted(players, key=lambda p: order.index(p["role"]) if p["role"] in order else 99)
    return {"players": players}

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
