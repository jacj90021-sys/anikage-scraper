#!/usr/bin/env python3
"""anikage-scraper - Flask web API around anikage_scraper.py."""

from flask import Flask, jsonify, request

from anikage_scraper import (fetch_episodes, get_anime_info, list_servers,
                             list_streams, resolve_stream, search_anime)

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
    the numeric AniList ID directly (GET /api/media/anime/<id>)."""
    try:
        return jsonify(get_anime_info(str(anilist_id)))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
