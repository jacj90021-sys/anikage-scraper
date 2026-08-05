#!/usr/bin/env python3
"""
flask_api_template.py — minimal Flask API mirroring the anikage/just4anime contract.

Endpoints:
  GET /api/anime/<anilistId>/servers?ep=<N>
      -> {"servers":[{"server","name","types":[...]}]}
  GET /api/anime/<anilistId>/stream?ep=<N>&server=<srv>&type=<sub|dub|hsub>&title=<t>
      -> {"url","referer","format","isM3U8","subtitles":[{"file","label"}], ...}
  GET /api/proxy?url=<vtt>     (same-origin subtitle proxy, text/vtt)
  GET /api/health

Bind to $PORT (Render requirement). Copy resolve_one() to plug in your own scraper.

An Android ExoPlayer app that already consumes this shape (anikage-scraper) can
consume ANY backend built on this template with zero app changes (M6).
"""
import os
import requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# Fill these from your scraper module
SERVER_TYPES = {
    "kai":  ["sub", "hsub", "dub"],
    "zeke": ["sub", "hsub", "dub"],
    "jin":  ["sub", "dub"],
    "ryuk": ["sub", "dub", "hsub"],
    "sai":  ["sub", "dub"],
    "mai":  ["sub", "dub"],
}
NAMES = {k: k.capitalize() for k in SERVER_TYPES}


def resolve_one(anilist_id, episode, server, typ, title=None):
    """RETURN A LIST of dicts: {url, referer, format, isM3U8, subtitles:[{file,label}]}.
    Replace this body with your actual scraper (see METHODS.md / sites/*.md)."""
    raise NotImplementedError("plug in your scraper here")


@app.route("/api/anime/<anilist_id>/servers")
def servers(anilist_id):
    ep = request.args.get("ep", "1")
    out = [{"server": s, "name": NAMES.get(s, s), "types": t}
           for s, t in SERVER_TYPES.items()]
    return jsonify({"anilistId": anilist_id, "episode": ep, "servers": out})


@app.route("/api/anime/<anilist_id>/stream")
def stream(anilist_id):
    ep = request.args.get("ep", "1")
    server = request.args.get("server")
    typ = request.args.get("type", "sub")
    title = request.args.get("title", "")
    if not server:
        return jsonify({"error": "missing 'server'"}), 400
    try:
        rows = resolve_one(anilist_id, ep, server, typ, title)
    except NotImplementedError:
        return jsonify({"error": "resolver not implemented"}), 501
    if not rows:
        return jsonify({"error": "no stream found"}), 404
    row = rows[0]
    row.update({"anilistId": anilist_id, "episode": ep, "server": server, "type": typ})
    return jsonify(row)


@app.route("/api/proxy")
def proxy():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing 'url'"}), 400
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        return Response(r.content, content_type="text/vtt")
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)
