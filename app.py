#!/usr/bin/env python3
"""anikage.cc Flask API — catalog + m3u8 stream resolver.

Endpoints (mirrors anidb-scraper / anidap-scraper shape):
  GET /api/health
  GET /api/search?q=<query>          -> {"results":[{id,slug,title,poster,...}]}
                                       (search = client-side filter on homepage index)
  GET /api/sources?slug=<slug>&ep=<n>&provider=<opt>
                                    -> {"m3u8":..., "referer":..., "providers":[...], ...}
"""
import html
import json
import re
import urllib.parse
import urllib.request
from flask import Flask, request, jsonify

from anikage_scraper import BASE, UA, get, scrape_homepage, api_get, resolve_stream

app = Flask(__name__)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "backend": "anikage", "site": BASE})


@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    try:
        # anikage search is a client-side filter over the homepage index
        rows = scrape_homepage()
        ql = q.lower()
        matched = [r for r in rows if ql in r["anime"].lower()]
        out = [{
            "id": r["slug"],
            "slug": r["slug"],
            "title": r["anime"],
            "poster": "",
            "type": "",
        } for r in matched]
        return jsonify({"results": out})
    except Exception as e:
        return jsonify({"error": "search failed", "details": str(e)}), 500


@app.route("/api/sources")
def sources():
    slug = request.args.get("slug", "").strip()
    ep = request.args.get("ep", "1").strip()
    provider = request.args.get("provider", "").strip() or None
    if not slug:
        return jsonify({"error": "missing slug"}), 400
    try:
        res = resolve_stream(slug, ep, provider)
        m3u8 = res.get("m3u8")
        if not m3u8:
            return jsonify({
                "error": "no m3u8 resolved",
                "source": "anikage",
                "slug": res.get("slug"),
                "episode": res.get("episode"),
                "providers": res.get("providers"),
                "details": res.get("error", "anikage returned no playable source"),
                "raw": res,
            }), 404
        return jsonify({
            "source": "anikage",
            "slug": res.get("slug"),
            "episode": res.get("episode"),
            "providers": res.get("providers"),
            "chosen_provider": res.get("provider"),
            "m3u8": m3u8,
            "referer": res.get("referer"),
            "embedUrl": res.get("embedUrl"),
            "raw": res,
        })
    except Exception as e:
        return jsonify({"error": "sources failed", "details": str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)
