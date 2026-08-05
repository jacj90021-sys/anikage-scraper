#!/usr/bin/env python3
"""
anikage.cc scraper  (corrected, verified resolver)
==================================================

Reverse-engineered from the LIVE anikage site (verified 2026-08 against
https://anikage.cc/anime/watch/ARPEGZW3fK?ep=1 and others).

HOW IT WORKS
------------
1) Catalog / server list (clean JSON API, needs only a Referer):
     GET /api/media/anime/<slug>/episodes
         -> {"anilistId":..,"total":N,"episodes":[{number,title,...}]}
     GET /api/media/anime/<slug>/episodes/<n>/servers
         -> {"servers":[{id,label,subTypes}], "embeds":[{id,key,label}]}

2) Stream resolution:
     GET /api/media/anime/<slug>/episodes/<n>/sources?provider=<id>&lang=<sub|dub>
         -> {"sources":[{url,isM3U8,embedUrl,quality,type}], "embeds":[{...}], ...}
   Every source url is base64( XOR with repeating key b"aproxy2026" ).
   Decrypting it yields the REAL upstream URL directly (no prox relay, no
   embed-page scraping). The same decrypt resolves every provider:

       neko -> https://vivibebe.site/public/stream/<hash>/master.m3u8   (hls)
       ken  -> https://vivibebe.site/public/stream/<hash>/master.m3u8   (hls, hardsub)
       megg -> https://s<nnn>.vidcache.net:<port>/play/<token>/video.mp4 (mp4)
       wave -> https://<cdn>.echovideo.to/cdn/<token>?t.m3u8             (hls)
       koto -> https://megap.<cdn>/<token>/<hash>/master.m3u8            (hls)
       dib  -> https://playeng.animeapps.top/...                         (hls)

   Note: a token sometimes carries TWO urls (primary + fallback); the
   primary (first) is used.

3) koto / wish (megaplay) extras: for these we also call the megaplay player
   endpoint to get the subtitle track and intro/outro skip times:
     GET https://megaplay.buzz/stream/getSources?id=<file_id>&h=0&m=0&type=sub
     (needs Referer + Origin = https://megaplay.buzz). The <file_id> is the
     data-id attribute on the embed page (megaplay.buzz/stream/s-<n>/<realid>/<type>)
     -- NOT the s-<n>/<realid> path number.

OUTPUT of resolve_stream:
  {slug, episode, lang, provider, url, referer, format, quality, title,
   subtitle, intro, outro, embed_url}
"""

import argparse
import base64
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://anikage.cc"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# The real XOR key for anikage's encrypted source tokens.
# (brute-forced from the known "https://" plaintext prefix in Aug 2026;
#  it rotates each year - proxy2024/2025 were previous values)
_TOKEN_KEY = b"aproxy2026"

# server id -> display name (matches the site's Servers row)
_DISPLAY = {"neko": "Neko", "ken": "Ken", "megg": "Megg",
            "wave": "Wave", "koto": "Koto", "dib": "Ken"}

# embed key -> backend provider it resolves to.
# Both softsub and hardsub embeds are the "neko" backend; the key only selects
# which source type (softsub/hardsub) is returned. (Player map Je: neko=softsub,
# ken=hardsub, both backend "neko".)
_EMBED_BACKEND = {"softsub": "neko", "hardsub": "neko",
                  "koto": "koto", "wish": "koto"}

_CACHE = {}


def _get(url, referer=None, raw=False, timeout=30):
    headers = {"User-Agent": UA,
               "Accept": "application/json, text/html, */*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if raw else data.decode("utf-8", "ignore")


def _api(path, referer):
    key = (path, referer)
    if key not in _CACHE:
        _CACHE[key] = json.loads(_get(f"{BASE}/api/{path}", referer))
    return _CACHE[key]


# ---------- catalog ----------

def scrape_homepage():
    h = _get(f"{BASE}/")
    infos = [(m.start(), m.group(1))
             for m in re.finditer(r'href="/anime/info/([A-Za-z0-9]+)"', h)]
    alts = []
    for m in re.finditer(r"<img[^>]+>", h):
        tag = m.group(0)
        am = re.search(r'alt="([^"]*)"', tag)
        sm = re.search(r'src="([^"]*anilistcdn[^"]*)"', tag)
        if am and sm:
            alts.append((m.start(), html.unescape(am.group(1))))
    out = []
    for ipos, slug in infos:
        cand = [a for ap, a in alts if ap < ipos]
        title = cand[-1] if cand else ""
        if title and slug:
            out.append({"slug": slug, "anime": title})
    seen, uniq = set(), []
    for r in out:
        if r["slug"] in seen:
            continue
        seen.add(r["slug"])
        uniq.append(r)
    return uniq


def fetch_episodes(slug):
    return _api(f"media/anime/{slug}/episodes",
                referer=f"{BASE}/anime/watch/{slug}")


def fetch_servers(slug, ep):
    return _api(f"media/anime/{slug}/episodes/{ep}/servers",
                referer=f"{BASE}/anime/watch/{slug}")


def fetch_sources(slug, ep, provider, lang="sub"):
    return _api(f"media/anime/{slug}/episodes/{ep}/sources"
                f"?provider={provider}&lang={lang}",
                referer=f"{BASE}/anime/watch/{slug}")


def list_servers(slug, ep):
    """Full server list, named exactly like the site:
    Servers: Neko, Ken, Megg, Wave, Koto - Embeds: E-Neko, E-Ken, E-Koto, E-Wish."""
    d = fetch_servers(slug, ep)
    out = {"slug": slug, "episode": ep, "servers": [], "embeds": []}
    for s in d.get("servers", []) or []:
        out["servers"].append({
            "id": s.get("id"),
            "name": _DISPLAY.get(s.get("id"), (s.get("id") or "").title()),
            "label": s.get("label"),
            "subTypes": s.get("subTypes") or ["sub"],
        })
    for e in d.get("embeds", []) or []:
        eid = e.get("id")
        out["embeds"].append({
            "id": eid,
            "label": e.get("label") or eid,
            "backend": _EMBED_BACKEND.get(eid, eid),
        })
    return out


# ---------- stream resolution ----------

def decrypt_token(tok):
    """base64decode then XOR with repeating _TOKEN_KEY. Returns a URL string
    (the primary/first URL if the token carries two) or None."""
    try:
        raw = base64.b64decode(tok + "=" * ((4 - len(tok) % 4) % 4))
    except Exception:
        return None
    plain = bytes([b ^ _TOKEN_KEY[i % len(_TOKEN_KEY)]
                   for i, b in enumerate(raw)]).rstrip(b"\x00")
    m = re.search(rb"https?://[^\x00-\x20\s]+", plain)
    if not m:
        return None
    urls = [u.decode("latin1").rstrip(".,;\"'")
            for u in re.findall(rb"https?://[^\x00-\x20\s]+", plain)]
    return urls[0]


def _pick_source(d, wanted_type=None):
    """Best source from a sources response. Prefers the default/first entry
    (highest quality), optionally filtered by type (sub/softsub/hardsub)."""
    srcs = d.get("sources", []) or []
    if not srcs:
        return None
    if wanted_type:
        for s in srcs:
            if s.get("type") == wanted_type:
                return s
    return srcs[0]


def megaplay_extras(embed_url):
    """Optional: megaplay getSources -> subtitle track + intro/outro.
    The file id is the data-id on the embed page (not the s-<n>/<realid>/ path
    number). Non-fatal if the player host is unreachable."""
    file_id = None
    try:
        page = _get(embed_url, referer=embed_url)
        m = re.search(r'data-id="(\d+)"', page)
        if m:
            file_id = m.group(1)
    except Exception:
        pass
    if not file_id:
        m = re.search(r"/stream/s-\d+/(\d+)", embed_url)
        file_id = m.group(1) if m else None
    if not file_id:
        return {}
    try:
        url = (f"https://megaplay.buzz/stream/getSources?id={file_id}"
               f"&h=0&m=0&type=sub")
        h = {"User-Agent": UA, "Referer": embed_url,
             "Origin": "https://megaplay.buzz",
             "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        out = {}
        tr = (d.get("tracks") or [])
        if tr and tr[0].get("file"):
            out["subtitle"] = tr[0]["file"]
            out["subtitle_label"] = tr[0].get("label")
        if d.get("intro"):
            out["intro"] = d["intro"]
        if d.get("outro"):
            out["outro"] = d["outro"]
        return out
    except Exception:
        return {}


def resolve_stream(slug, ep, provider=None, lang="sub"):
    """Resolve a playable stream for slug/ep. `provider` may be a server id
    (neko/ken/megg/wave/koto/dib) or a display name (E-Neko, E-Ken, ...)."""
    wanted = "dub" if lang == "dub" else "sub"
    servers = list_servers(slug, ep)
    providers = servers["servers"]
    embeds = servers["embeds"]

    if not providers and not embeds:
        return {"slug": slug, "episode": ep, "error": "no servers for this episode"}

    # Build the ordered list of (label, backend_provider, kind, key) to try.
    plan = []
    for s in providers:
        sub_types = s.get("subTypes") or []
        if wanted == "dub" and "dub" not in sub_types:
            continue
        plan.append((s["name"], s["id"], "provider", None))
    for e in embeds:
        plan.append((e["label"], e["backend"], "embed", e["id"]))

    # Reorder: requested provider first.
    if provider:
        hit = [p for p in plan
               if provider in (p[1], p[0]) or provider.lower() in p[0].lower()]
        plan = hit + [p for p in plan if p not in hit]
        if not hit:
            return {"slug": slug, "episode": ep,
                    "error": f"unknown server: {provider}"}

    errors = []
    for label, backend, kind, key in plan:
        try:
            d = fetch_sources(slug, ep, backend, wanted)
        except Exception as ex:
            errors.append(f"{label}: sources failed ({ex})")
            continue

        # --- primary path: decrypt the encrypted source url ---
        want_type = key if kind == "embed" else None
        if want_type is None and backend == "neko" and wanted == "sub":
            want_type = "softsub"          # Neko's default is softsub
        src = _pick_source(d, wanted_type=want_type)
        if src and src.get("url"):
            real = decrypt_token(src["url"])
            if real:
                res = {
                    "slug": slug,
                    "episode": ep,
                    "lang": wanted,
                    "provider": label,
                    "quality": src.get("quality"),
                    "url": real,
                    "format": "mp4" if not src.get("isM3U8") else "hls",
                    "referer": f"{urllib.parse.urlsplit(real).scheme}://"
                               f"{urllib.parse.urlsplit(real).netloc}/",
                    "embed_url": src.get("embedUrl"),
                }
                # koto/wish -> try to attach subtitle + intro/outro
                if backend in ("koto",) and src.get("embedUrl"):
                    res.update(megaplay_extras(src["embedUrl"]))
                return res
            errors.append(f"{label}: token decrypt failed")
            continue

        # --- fallback: walk the source / embed urls looking for a decryptable hls ---
        emb_list = d.get("embeds", []) or []
        candidates = [s for s in d.get("sources", []) if s.get("embedUrl")]
        candidates += [e for e in emb_list if e.get("url")]
        for cand in candidates:
            u = cand.get("url") or cand.get("embedUrl")
            if not u:
                continue
            real = decrypt_token(u)
            if real:
                return {"slug": slug, "episode": ep, "lang": wanted,
                        "provider": label, "quality": cand.get("quality"),
                        "url": real, "format": "hls",
                        "referer": f"{urllib.parse.urlsplit(real).scheme}://"
                                   f"{urllib.parse.urlsplit(real).netloc}/",
                        "embed_url": cand.get("embedUrl") or cand.get("url")}
            errors.append(f"{label}: no decryptable stream")
            break
        else:
            errors.append(f"{label}: no stream entries")
        # rate-limit courtesy between providers
        time.sleep(0.3)

    return {"slug": slug, "episode": ep, "error": "; ".join(errors)
            or "no server yielded a stream"}


def main():
    ap = argparse.ArgumentParser(description="anikage.cc scraper")
    ap.add_argument("--search")
    ap.add_argument("--slug")
    ap.add_argument("--episodes", action="store_true")
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--ep", default="1")
    ap.add_argument("--provider")
    ap.add_argument("--lang", default="sub", choices=["sub", "dub"])
    ap.add_argument("--out", default="anikage_index")
    args = ap.parse_args()

    if args.stream:
        if not args.slug:
            print("ERROR: --slug required for --stream", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(resolve_stream(args.slug, args.ep,
                                        args.provider, args.lang),
                         indent=2, ensure_ascii=False))
        return

    if args.episodes and args.slug:
        d = fetch_episodes(args.slug)
        eps = d.get("episodes", [])
        print(f"slug {args.slug}: total={d.get('total')} episodes={len(eps)}")
        for e in eps[:10]:
            print(f"  ep{e['number']}: {e.get('title')}")
        return

    rows = scrape_homepage()
    if args.search:
        q = args.search.lower()
        rows = [r for r in rows if q in r["anime"].lower()]
    json.dump(rows, open(args.out + ".json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"matched {len(rows)} -> {args.out}.json")
    for r in rows[:10]:
        print(f"  [{r['slug']}] {r['anime']}")


if __name__ == "__main__":
    main()
