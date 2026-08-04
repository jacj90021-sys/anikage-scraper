#!/usr/bin/env python3
"""anikage.cc Flask API — catalog + m3u8 stream resolver.

EXACT-MATCH design (no title guessing, no per-search homepage scrape):
  anikage.cc has NO search API. Its episode endpoint returns the AniList ID
  for a slug (e.g. /api/media/anime/<slug>/episodes -> {"anilistId": 169583}).
  So we build an `anilistId -> slug` index ONCE (server-side, cached to disk)
  by crawling the ~70 homepage slugs and reading each one's anilistId. The app
  then resolves a stream by sending the AniList ID it already has — guaranteeing
  the correct anime, never a wrong-title guess.

Endpoints (mirrors anidb-scraper / anidap-scraper shape):
  GET /api/health
  GET /api/search?q=<query>          -> {"results":[{"slug","anime",...}]}  (title filter, best-effort)
  GET /api/sources?slug=<slug>&ep=<n>             -> {m3u8, referer, providers}
  GET /api/sources?id=<anilistId>&ep=<n>          -> exact: id->slug->m3u8
"""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from flask import Flask, request, jsonify

from anikage_scraper import BASE, UA, api_get, scrape_homepage, resolve_stream, fetch_servers, _all_providers

# anikage's embeds need a Referer from the embed host; resolve_stream returns the
# correct per-embed referer. This is just a fallback default.
REFERER = f"{BASE}/"

app = Flask(__name__)

INDEX_FILE = os.path.join(os.path.dirname(__file__), "anikage_index.json")
_index = {}          # anilistId (int) -> slug
_index_lock = threading.Lock()
_index_built_at = 0


def _slug_anilist(slug):
    """Read the anilistId for a slug from anikage's episode API (retry on 429)."""
    for attempt in range(4):
        try:
            d = api_get(f"media/anime/{slug}/episodes",
                        referer=f"{BASE}/anime/watch/{slug}")
            aid = d.get("anilistId")
            return int(aid) if aid else None
        except Exception as e:
            if "429" in str(e) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            return None
    return None


def build_index(force=False):
    """Build anilistId->slug map once and cache to disk. Thread-safe, debounced."""
    global _index, _index_built_at
    with _index_lock:
        if not force and _index and (time.time() - _index_built_at) < 6 * 3600:
            return _index
        # try load from disk first
        if not force and os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE) as f:
                    _index = {int(k): v for k, v in json.load(f).items()}
                _index_built_at = time.time()
                return _index
            except Exception:
                pass
        new_index = {}
        for item in scrape_homepage():
            slug = item.get("slug")
            if not slug:
                continue
            aid = _slug_anilist(slug)
            if aid:
                new_index[aid] = slug
            time.sleep(0.5)  # avoid anikage rate-limiting during the one-time crawl
        if new_index:
            _index = new_index
            _index_built_at = time.time()
            try:
                with open(INDEX_FILE, "w") as f:
                    json.dump({str(k): v for k, v in _index.items()}, f)
            except Exception:
                pass
    return _index


@app.route("/api/health")
def health():
    return jsonify({"backend": "anikage", "site": BASE, "status": "ok"})


@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    items = scrape_homepage()
    ql = q.lower()
    # exact > startswith > substring; prefer shortest title (canonical series)
    def score(t):
        tl = (t or "").lower()
        if tl == ql:
            return 0
        if tl.startswith(ql):
            return 1
        if ql in tl:
            return 2
        return 3
    matched = [r for r in items if ql in (r.get("anime") or "").lower()]
    matched.sort(key=lambda r: (score(r.get("anime")), len(r.get("anime") or "")))
    return jsonify({"query": q, "results": matched[:10]})


@app.route("/api/sources")
def sources():
    slug = request.args.get("slug")
    anilist_id = request.args.get("id")
    ep = request.args.get("ep", "1")
    audio_type = request.args.get("type", "sub")          # "sub" | "dub"
    audio_type = "dub" if audio_type.lower().startswith("d") else "sub"

    if anilist_id:
        # EXACT path: anilist id -> slug via cached index (no title guessing)
        try:
            aid = int(anilist_id)
        except ValueError:
            return jsonify({"error": "id must be an integer anilist id"}), 400
        idx = build_index()
        slug = idx.get(aid)
        if not slug:
            return jsonify({"error": f"anilist id {aid} not found on anikage (index has {len(idx)} titles)",
                             "source": "anikage"}), 404

    if not slug:
        return jsonify({"error": "missing slug or id"}), 400
    try:
        ep_n = int(ep)
    except ValueError:
        return jsonify({"error": "ep must be an integer"}), 400

    try:
        res = resolve_stream(slug, ep_n, type=audio_type)
    except Exception as e:
        return jsonify({"error": f"resolve failed: {e}", "source": "anikage"}), 502

    m3u8 = res.get("m3u8")
    if not m3u8:
        # anikage returns empty when the requested type (e.g. dub) isn't available
        # for this episode. Surface it honestly — do NOT silently fall back to sub.
        return jsonify({"error": f"no {audio_type} stream resolved for this episode on anikage",
                        "source": "anikage", "type": audio_type,
                        "slug": slug, "providers": res.get("providers", [])}), 404

    # Normalize to the same shape the app expects from anidb/anizone:
    return jsonify({
        "source": "anikage",
        "slug": slug,
        "episode": ep_n,
        "type": audio_type,
        "m3u8": m3u8,
        "referer": res.get("referer") or REFERER,
        "chosen_provider": res.get("provider"),
        "embedUrl": res.get("embedUrl"),
        "providers": res.get("providers", []),
    })


@app.route("/api/servers")
def servers_route():
    """List providers for an episode WITH their subTypes, so the app can filter
    by sub/dub. Resolved by anilist id or slug (exact)."""
    slug = request.args.get("slug")
    anilist_id = request.args.get("id")
    ep = request.args.get("ep", "1")
    if anilist_id:
        try:
            aid = int(anilist_id)
        except ValueError:
            return jsonify({"error": "id must be an integer anilist id"}), 400
        idx = build_index()
        slug = idx.get(aid)
        if not slug:
            return jsonify({"error": f"anilist id {aid} not found on anikage", "source": "anikage"}), 404
    if not slug:
        return jsonify({"error": "missing slug or id"}), 400
    try:
        ep_n = int(ep)
    except ValueError:
        return jsonify({"error": "ep must be an integer"}), 400
    try:
        srvs = _all_providers(slug, ep_n)
    except Exception as e:
        return jsonify({"error": f"servers failed: {e}", "source": "anikage"}), 502
    out = [{"id": s.get("id"), "name": s.get("label") or s.get("id"),
            "subTypes": s.get("subTypes", ["sub"])} for s in srvs]
    return jsonify({"slug": slug, "episode": ep_n, "servers": out})


if __name__ == "__main__":
    import os as _os
    port = int(_os.environ.get("PORT", "3000"))
    # warm the index in the background so first id-lookup is fast
    threading.Thread(target=build_index, daemon=True).start()
    app.run(host="0.0.0.0", port=port)
