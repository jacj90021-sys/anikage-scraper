#!/usr/bin/env python3
"""anikage-scraper - Flask web API around anikage_scraper.py."""

import time

from flask import Flask, jsonify, request

from anikage_scraper import (fetch_episodes, list_servers, list_streams,
                             resolve_stream, scrape_homepage)

app = Flask(__name__)
INDEX_CACHE = None
INDEX_TTL = 0


def _index():
    """Homepage catalog, cached for 5 minutes (rate-limit friendly)."""
    global INDEX_CACHE, INDEX_TTL
    if INDEX_CACHE is None or time.time() > INDEX_TTL:
        INDEX_CACHE = scrape_homepage()
        INDEX_TTL = time.time() + 300
    return INDEX_CACHE


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/search")
def search():
    q = (request.args.get("q") or "").strip().lower()
    rows = _index()
    if q:
        rows = [r for r in rows if q in r["anime"].lower()]
    return jsonify({"count": len(rows), "results": rows[:50]})


@app.get("/api/anime/<slug>/episodes")
def episodes(slug):
    try:
        return jsonify(fetch_episodes(slug))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/anime/<slug>/servers")
def servers(slug):
    ep = request.args.get("ep", "1")
    try:
        return jsonify(list_servers(slug, ep))
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
    try:
        return jsonify(resolve_stream(slug, ep, provider, lang))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
