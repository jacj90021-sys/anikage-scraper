#!/usr/bin/env python3
"""anikage-scraper - Flask web API around anikage_scraper.py."""

from flask import Flask, jsonify, request
import urllib.request

from anikage_scraper import (fetch_episodes, get_anime_info, list_servers,
                             list_streams, resolve_by_id, resolve_stream,
                             search_anime)

app = Flask(__name__)


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/search")
def search():
    q = request.args.get("q") or ""
    try:
        return jsonify({"count": len(search_anime(q)),
                        "results": search_anime(q)})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/anime/by-id/<int:anilist_id>")
def anime_by_id(anilist_id):
    """Resolve an anikage slug + metadata from an AniList ID. anikage accepts
    the numeric AniList ID directly (GET /api/media/anime/<id>), but for some
    shows its stored anilistId differs from AniList's, so pass `?title=` and
    the backend falls back to a live title search."""
    title = request.args.get("title")
    try:
        return jsonify(resolve_by_id(anilist_id, title))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 404


@app.get("/api/anime/<slug>")
def anime_info(slug):
    try:
        return jsonify(get_anime_info(slug))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/anime/<slug>/episodes")
def episodes(slug):
    try:
        return jsonify(fetch_episodes(slug))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/anime/<slug>/servers")
def servers(slug):
    ep = request.args.get("ep", "1")
    lang = request.args.get("lang", "sub")
    try:
        return jsonify(list_servers(slug, ep, lang))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/anime/<slug>/streams")
def streams(slug):
    ep = request.args.get("ep", "1")
    try:
        return jsonify(list_streams(slug, ep))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/anime/<slug>/stream")
def stream(slug):
    ep = request.args.get("ep", "1")
    provider = request.args.get("provider")
    lang = request.args.get("lang", "sub")
    quality = request.args.get("quality")
    try:
        return jsonify(resolve_stream(slug, ep, provider, lang, quality))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/proxy")
def proxy():
    """Same-origin subtitle proxy. Several anikage CDN hosts (e.g.
    1oe.lostproject.club) return HTTP 403 to direct device/browser fetches
    (hotlink protection) but are reachable server-side. We fetch here and
    stream the bytes back so the Android player can load subtitles same-origin,
    exactly like the anizone backend does. Anime subtitle MIME is forced to
    text/vtt so ExoPlayer parses it."""
    target = request.args.get("url")
    if not target or not target.startswith("http"):
        return jsonify({"error": "missing url"}), 400
    try:
        req = urllib.request.Request(
            target,
            headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0.0.0 Safari/537.36"),
                "Referer": "https://megaplay.buzz/",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        from flask import Response
        return Response(data, mimetype="text/vtt")
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
