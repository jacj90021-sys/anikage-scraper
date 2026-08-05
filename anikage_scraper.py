#!/usr/bin/env python3
"""
anikage.cc scraper  (corrected, verified resolver)
==================================================

Reverse-engineered from the LIVE anikage site (verified 2026-08 against
https://anikage.cc/anime/watch/ARPEGZW3fK?ep=1 and Witch Hat Atelier
5irZy5W2tW).

HOW IT WORKS
------------
1) Catalog / server list (clean JSON API, needs only a Referer):
     GET /api/media/anime/<slug>/episodes
         -> {"anilistId":..,"total":N,"episodes":[{number,title,...}]}
     GET /api/media/anime/<slug>/episodes/<n>/servers
         -> {"servers":[{id,label,subTypes}], "embeds":[{id,key,label}]}

   "servers" = the site's Servers row (Neko / Ken / Miko / Dib / Wave / Koto).
   "embeds"  = the site's Embeds row (E-Neko / E-Ken / E-Koto / E-Wish). The
   embeds are DISTINCT entries on the site and resolve to different selections
   of the same underlying backends:
     E-Neko -> neko backend, softsub sources
     E-Ken  -> neko backend, hardsub sources
     E-Koto -> koto backend, megaplay sources (HD-1)
     E-Wish -> koto backend, vidtube sources (VidPlay-1)

2) Stream resolution:
     GET /api/media/anime/<slug>/episodes/<n>/sources?provider=<id>&lang=<sub|dub>
         -> {"sources":[{url,isM3U8,embedUrl,quality,type}], "embeds":[...] }
   Every source url is base64( XOR with repeating key b"aproxy2026" ).
   Decrypting it yields the REAL upstream URL directly (no prox relay, no
   embed-page scraping). Each provider exposes MULTIPLE sources = the site's
   quality menu (Softsub HD-1, Hardsub HD-2, Dub HD-1, 1080p/720p/480p,
   SR auto, Vidplay auto, HD-1 auto, VidPlay-1 auto).

   Every CDN host enforces a Referer and they are NOT the same for all hosts.
   The correct referer is derived from the EMBED URL origin (the player page):
     neko    vivibebe.site / bibiemb.xyz       -> that host
     ken/dib playeng.animeapps.top             -> that host
     wave    echovideo cdn host                -> https://play.echovideo.ru/
     koto    megap.<cdn>/.../master.m3u8       -> https://megaplay.buzz/
     koto    vidtub.<cdn>/.../master.m3u8      -> https://vidtube.site/
     megg    vidcache.net:<port>/...mp4        -> https://vidcache.net/

3) koto / wish (megaplay) extras: subtitle track + intro/outro via
     GET https://megaplay.buzz/stream/getSources?id=<file_id>&h=0&m=0&type=sub
   (needs Referer + Origin = https://megaplay.buzz). The <file_id> is the
   data-id attribute on the embed page (megaplay.buzz/stream/s-<n>/<realid>/<type>).
   neko softsub/dub attach their VTT subtitle via the `sub=` query param on the
   embed url instead (https://cdn.anizara.store/.../....vtt, open to any UA).

OUTPUT of resolve_stream:
  {slug, episode, lang, provider, quality, type, url, referer, format,
   subtitle, subtitle_label, intro, outro, embed_url}
"""

import argparse
import base64
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://anikage.cc"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# The real XOR key for anikage's encrypted source tokens.
# (brute-forced from the known "https://" plaintext prefix in Aug 2026;
#  it rotates each year - proxy2024/2025 were previous values)
_TOKEN_KEY = b"aproxy2026"

# server id -> display name (matches the site's Servers row)
_DISPLAY = {"neko": "Neko", "megg": "Megg", "dib": "Dib",
             "wave": "Wave", "koto": "Koto", "ken": "Ken"}

# embed id -> (backend provider, source type filter, embed-host filter)
# The embeds are the site's Embeds row; each maps to a DISTINCT source pick.
_EMBED_BACKEND = {"softsub": ("neko", "softsub", None),
                  "hardsub": ("neko", "hardsub", None),
                  "koto": ("koto", None, "megaplay"),
                  "wish": ("koto", None, "vidtube")}

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

def search_anime(q, limit=25):
    """Find anime by keyword using anikage's real browse/search API
    (GET /api/media/anime/browse?q=..&sort=popularity&page=1&limit=..).
    NOT a hardcoded list - the catalog is fetched live from the site.
    Every result carries anilistId (anikage's metadata source is AniList)."""
    params = {"q": q, "sort": "popularity", "page": 1,
              "limit": limit, "adult": "false"}
    url = f"{BASE}/api/media/anime/browse?" + urllib.parse.urlencode(params)
    d = json.loads(_get(url, referer=f"{BASE}/"))
    out = []
    for x in d.get("data", []) or []:
        t = x.get("title") or {}
        title = (t.get("english") or t.get("romaji")
                 or t.get("native") or x.get("name") or "")
        out.append({
            "slug": x.get("slug"),
            "anilistId": x.get("anilistId"),
            "anime": title,
            "title_english": t.get("english") or title,
            "title_romaji": t.get("romaji") or title,
            "title_native": t.get("native") or title,
            "format": x.get("format"),
            "year": x.get("year"),
            "status": x.get("status"),
            "popularity": x.get("popularity") or 0,
            "cover": (x.get("coverImage") or {}).get("large"),
        })
    return out


def get_anime_info(slug):
    """Full metadata for a slug from GET /api/media/anime/<slug>.
    Includes anilistId / malId - anikage's data comes from AniList."""
    return _api(f"media/anime/{slug}", referer=f"{BASE}/anime/info/{slug}")


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _title_search_match(title, anilist_id):
    """Find the anikage entry that best matches a title (and/or AniList id).
    anikage's stored anilistId can differ from AniList's own id for some
    shows (e.g. Korean titles), so the numeric id lookup can 502 - fall back
    to a live title search and score candidates: exact title wins, an
    anilistId hit is a strong bonus, then popularity."""
    tn = _norm(title)
    best, best_score = None, -1
    for r in search_anime(title, limit=25):
        score = 0
        if r.get("anilistId") and str(r["anilistId"]) == str(anilist_id):
            score += 1000
        for k in ("anime", "title_english", "title_romaji", "title_native"):
            rn = _norm(r.get(k) or "")
            if tn and rn == tn:
                score += 100
            elif tn and rn and (tn in rn or rn in tn):
                score += 30
        score += min((r.get("popularity") or 0) // 100000, 10)
        if score > best_score:
            best, best_score = r, score
    if best is None or best_score < 30:
        return None
    return best


def resolve_by_id(anilist_id, title=None):
    """Full metadata for an AniList id. Fast path: anikage accepts the numeric
    AniList id as a slug. If that 502s (anikage stores a different anilistId,
    common for Korean titles) or returns a different show, fall back to a live
    title search on anikage's own browse API."""
    if title is None:
        title = ""
    try:
        d = get_anime_info(str(anilist_id))
        got = (d.get("anime") or {}).get("anilistId")
        if got is None or str(got) == str(anilist_id):
            return d
    except Exception:
        pass
    if title:
        m = _title_search_match(title, anilist_id)
        if m and m.get("slug"):
            d = get_anime_info(m["slug"])
            d["_matched_by"] = "title"
            return d
    raise RuntimeError(f"anikage: no anime found for AniList id {anilist_id}")


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


def _clean_quality(q):
    """'softsub HD-1' -> 'Softsub HD-1' (the site's display form)."""
    if not q:
        return None
    s = str(q).strip()
    return s[0].upper() + s[1:] if s else None


def _referer_for(url, embed_url=None):
    """The CDN referer is the PLAYER page origin, not the CDN host."""
    if embed_url:
        u = urllib.parse.urlsplit(embed_url)
        if u.netloc:
            return f"{u.scheme}://{u.netloc}/"
    u = urllib.parse.urlsplit(url)
    host = (u.netloc or "").lower()
    if "vidcache" in host:
        return "https://vidcache.net/"
    if host.startswith("megap."):
        return "https://megaplay.buzz/"
    if host.startswith("vidtub"):
        return "https://vidtube.site/"
    if "echovideo" in host:
        return "https://play.echovideo.ru/"
    return f"{u.scheme}://{u.netloc}/"


def _unique(seq):
    seen, out = set(), []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _provider_sources(slug, ep, backend, lang):
    """All decrypted sources for one backend provider + audio lang, each with
    its real referer. Deduped by (quality, embed_url)."""
    d = fetch_sources(slug, ep, backend, lang)
    out, seen = [], set()
    for s in d.get("sources", []) or []:
        real = decrypt_token(s.get("url"))
        if not real:
            continue
        q = _clean_quality(s.get("quality"))
        key = (q, s.get("embedUrl") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "quality": q,
            "type": s.get("type"),
            "format": "mp4" if not s.get("isM3U8") else "hls",
            "url": real,
            "referer": _referer_for(real, s.get("embedUrl")),
            "embed_url": s.get("embedUrl"),
        })
    return out


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


def _filter_sources(srcs, want_type, host_substr):
    if want_type:
        typed = [x for x in srcs if x["type"] == want_type]
        if typed:
            srcs = typed
    if host_substr:
        hostm = [x for x in srcs if host_substr in (x["embed_url"] or "")]
        if hostm:
            srcs = hostm
    return srcs


def _result(slug, ep, wanted, display, backend, pick):
    res = {"slug": slug, "episode": ep, "lang": wanted,
           "provider": display,
           "quality": pick["quality"],
           "type": pick["type"],
           "url": pick["url"],
           "format": pick["format"],
           "referer": pick["referer"],
           "embed_url": pick["embed_url"]}
    eu = pick.get("embed_url") or ""
    if backend == "koto" and "megaplay" in eu:
        res.update(megaplay_extras(eu))
    else:
        p = urllib.parse.parse_qs(urllib.parse.urlsplit(eu).query)
        if p.get("sub"):
            res["subtitle"] = p["sub"][0]
            res["subtitle_label"] = "English"
    return res


def _emit(slug, ep, wanted, display, backend, want_type, host_substr,
          srcs, quality):
    srcs = _filter_sources(srcs, want_type, host_substr)
    if not srcs:
        return {"slug": slug, "episode": ep,
                "error": f"{display}: no {wanted} sources"}
    if quality:
        for x in srcs:
            if (x.get("quality") or "").lower() == quality.lower():
                return _result(slug, ep, wanted, display, backend, x)
        for x in srcs:
            if quality.lower() in (x.get("quality") or "").lower():
                return _result(slug, ep, wanted, display, backend, x)
        avail = [x["quality"] for x in srcs if x.get("quality")]
        return {"slug": slug, "episode": ep,
                "error": f"quality '{quality}' not available for {display} "
                         f"({wanted}); options: {', '.join(avail)}"}
    if backend == "neko" and wanted != "dub" and want_type is None:
        soft = [x for x in srcs if x["type"] == "softsub"]
        if soft:
            return _result(slug, ep, wanted, display, backend, soft[0])
    return _result(slug, ep, wanted, display, backend, srcs[0])


def _normalize(servers, embeds, provider):
    """Match a provider token (server id, display name, embed id, embed label)
    to (display_name, backend, want_type, host_substr)."""
    if not provider:
        return None
    p = str(provider)
    if p.lower() == "ken":
        return ("Ken", "neko", "hardsub", None)
    for s in servers:
        if p in (s["provider"], s["name"]) or p.lower() in (s["name"] or "").lower():
            return (s["name"], s["provider"], None, None)
    for e in embeds:
        if p in (e["provider"], e["name"]) or p.lower() in (e["name"] or "").lower():
            backend, wtype, host = _EMBED_BACKEND.get(e["backend"], (e["backend"], None, None))
            return (e["name"], backend, wtype, host)
    return None


def list_servers(slug, ep, lang="sub"):
    """The site's full server+embed rows, each with the real quality labels for
    the requested audio lang. All 5 servers and all 4 embeds are always listed
    (Ken shows even though it is hardsub/SR-only) - exactly like the site."""
    want = "dub" if lang == "dub" else "sub"
    d = fetch_servers(slug, ep)
    servers, embeds = [], []

    def server_entry(s):
        sid = s.get("id")
        return {"provider": sid,
                "name": _DISPLAY.get(sid, (sid or "").title()),
                "label": s.get("label"),
                "subTypes": s.get("subTypes") or ["sub"],
                "qualities": [x["quality"] for x in
                              _provider_sources(slug, ep, sid, want)]}

    def embed_entry(e):
        eid = e.get("id")
        backend, wtype, host = _EMBED_BACKEND.get(eid, (eid, None, None))
        srcs = _filter_sources(_provider_sources(slug, ep, backend, want),
                               wtype, host)
        return {"provider": e.get("label") or eid,
                "name": e.get("label") or eid,
                "backend": eid,
                "qualities": [x["quality"] for x in srcs]}

    s_list = d.get("servers", []) or []
    e_list = d.get("embeds", []) or []
    with ThreadPoolExecutor(max_workers=3) as ex:
        s_futs = [ex.submit(server_entry, s) for s in s_list]
        e_futs = [ex.submit(embed_entry, e) for e in e_list]
        for f in s_futs:
            try:
                servers.append(f.result())
            except Exception:
                pass
        for f in e_futs:
            try:
                embeds.append(f.result())
            except Exception:
                pass
    ken_srcs = _filter_sources(_provider_sources(slug, ep, "neko", want),
                                "hardsub", None)
    servers.append({"provider": "ken",
                     "name": "Ken",
                     "label": "Koe no Katachi",
                     "subTypes": ["sub"],
                     "qualities": [x["quality"] for x in ken_srcs]})
    return {"slug": slug, "episode": int(ep) if str(ep).isdigit() else ep,
            "lang": want, "servers": servers, "embeds": embeds}


def resolve_stream(slug, ep, provider=None, lang="sub", quality=None):
    """Resolve ONE playable stream for slug/ep. `provider` may be a server id
    (neko/megg/dib/wave/koto/ken), a display name (Ken, Wave, ...), or an embed
    label (E-Neko, E-Ken, E-Koto, E-Wish). `quality` picks a specific source
    from the provider's quality menu for the requested lang."""
    wanted = "dub" if lang == "dub" else "sub"
    d = fetch_servers(slug, ep)
    servers = [{"provider": s.get("id"),
                "name": _DISPLAY.get(s.get("id"), (s.get("id") or "").title())}
               for s in d.get("servers", []) or []]
    servers.append({"provider": "ken", "name": "Ken"})
    embeds = [{"provider": e.get("label") or e.get("id"),
               "name": e.get("label") or e.get("id"),
               "backend": e.get("id")}
              for e in d.get("embeds", []) or []]

    if provider:
        norm = _normalize(servers, embeds, provider)
        if not norm:
            return {"slug": slug, "episode": ep,
                    "error": f"unknown server: {provider}"}
        display, backend, wtype, host = norm
        srcs = _provider_sources(slug, ep, backend, wanted)
        return _emit(slug, ep, wanted, display, backend, wtype, host,
                     srcs, quality)

    # default (no provider): first server that yields a stream, then embeds.
    for s in servers:
        srcs = _provider_sources(slug, ep, s["provider"], wanted)
        res = _emit(slug, ep, wanted, s["name"], s["provider"], None, None,
                    srcs, None)
        if res and "error" not in res:
            return res
    for e in embeds:
        backend, wtype, host = _EMBED_BACKEND.get(e["backend"], (e["backend"], None, None))
        srcs = _provider_sources(slug, ep, backend, wanted)
        res = _emit(slug, ep, wanted, e["name"], backend, wtype, host,
                    srcs, None)
        if res and "error" not in res:
            return res

    return {"slug": slug, "episode": ep, "error": "no server yielded a stream"}


def list_streams(slug, ep, langs=("sub", "dub")):
    """EVERYTHING an episode offers: every server/embed x every audio lang x
    every source/quality, all decrypted to real playable URLs + referers."""
    info = list_servers(slug, ep, langs[0])
    out = {"slug": slug, "episode": int(ep) if str(ep).isdigit() else ep,
           "servers": [], "embeds": []}
    for s in info["servers"]:
        entry = {"provider": s["provider"], "name": s["name"],
                 "subTypes": s["subTypes"], "sources": []}
        backend = "neko" if s["provider"] == "ken" else s["provider"]
        for lang in langs:
            want = "dub" if lang == "dub" else "sub"
            srcs = _provider_sources(slug, ep, backend, want)
            if s["provider"] == "ken":
                srcs = _filter_sources(srcs, "hardsub", None)
            for x in srcs:
                entry["sources"].append({"lang": lang, **x})
        out["servers"].append(entry)
    for e in info["embeds"]:
        backend, wtype, host = _EMBED_BACKEND.get(e["backend"], (e["backend"], None, None))
        entry = {"provider": e["provider"], "name": e["name"], "sources": []}
        for lang in langs:
            want = "dub" if lang == "dub" else "sub"
            srcs = _filter_sources(_provider_sources(slug, ep, backend, want),
                                   wtype, host)
            for x in srcs:
                entry["sources"].append({"lang": lang, **x})
        out["embeds"].append(entry)
    return out


def main():
    ap = argparse.ArgumentParser(description="anikage.cc scraper")
    ap.add_argument("--search")
    ap.add_argument("--slug")
    ap.add_argument("--episodes", action="store_true")
    ap.add_argument("--info", action="store_true",
                    help="show full metadata (anilistId, images, stats) for --slug")
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="dump EVERY stream (all servers x sub/dub x qualities)")
    ap.add_argument("--ep", default="1")
    ap.add_argument("--provider")
    ap.add_argument("--quality")
    ap.add_argument("--lang", default="sub", choices=["sub", "dub"])
    ap.add_argument("--out", default="anikage_index")
    args = ap.parse_args()

    if args.all:
        if not args.slug:
            print("ERROR: --slug required for --all", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(list_streams(args.slug, args.ep),
                         indent=2, ensure_ascii=False))
        return

    if args.stream:
        if not args.slug:
            print("ERROR: --slug required for --stream", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(resolve_stream(args.slug, args.ep,
                                        args.provider, args.lang,
                                        args.quality),
                         indent=2, ensure_ascii=False))
        return

    if args.info:
        if not args.slug:
            print("ERROR: --slug required for --info", file=sys.stderr)
            sys.exit(1)
        info = get_anime_info(args.slug)
        a = info.get("anime", info)
        t = a.get("title") or {}
        print(json.dumps({
            "slug": a.get("slug"),
            "anilistId": a.get("anilistId"),
            "malId": a.get("malId"),
            "title": t.get("english") or t.get("romaji") or t.get("native"),
            "native": t.get("native"),
            "format": a.get("format"),
            "status": a.get("status"),
            "year": a.get("year"),
            "season": a.get("season"),
            "episodes": a.get("totalEpisodes"),
            "genres": a.get("genres"),
            "cover": (a.get("coverImage") or {}).get("extraLarge"),
            "banner": a.get("bannerImage"),
            "synopsis": a.get("description"),
            "anilistStats": a.get("anilistStats"),
        }, indent=2, ensure_ascii=False))
        return

    if args.episodes and args.slug:
        d = fetch_episodes(args.slug)
        eps = d.get("episodes", [])
        print(f"slug {args.slug}: total={d.get('total')} episodes={len(eps)}")
        for e in eps[:10]:
            print(f"  ep{e['number']}: {e.get('title')}")
        return

    rows = search_anime(args.search or "", limit=25)
    json.dump(rows, open(args.out + ".json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"matched {len(rows)} -> {args.out}.json")
    for r in rows[:10]:
        print(f"  [{r['slug']}] {r['anime']}")


if __name__ == "__main__":
    main()
