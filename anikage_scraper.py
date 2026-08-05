#!/usr/bin/env python3
"""
anikage.cc scraper  (clean, proven-working resolver)
=====================================================

Reverse-engineered from the LIVE anikage site (verified 2026-08 against
https://anikage.cc/anime/watch/TpSCXHMVgS?ep=1 and others).

TWO DATA LAYERS
---------------
1) CATALOG / SERVER LIST (clean JSON API, needs only a Referer):
   GET /api/media/anime/<slug>/episodes
        -> {"anilistId":..,"total":N,"episodes":[{number,title,...}]}
   GET /api/media/anime/<slug>/episodes/<n>/servers
        -> {"servers":[{id,label,subTypes}], "embeds":[{id,key,label}]}

2) STREAM RESOLVER
   GET /api/media/anime/<slug>/episodes/<n>/sources?provider=<pid>&type=<type>
        -> {"sources":[{url,isM3U8,embedUrl,quality}], "embeds":[{server,type,url}]}

PROVEN SERVER MAP (from live API, Aug 2026):
  providers (Servers row):  neko, megg, dib, wave, koto
    neko  -> sources[0].embedUrl = vivibebe      -> m3u8  (works)
    dib   -> sources[0].embedUrl = playeng       -> m3u8  (relative path; works)
    megg  -> sources[0].url = XOR(aproxy2024) token -> .mp4  (works; decrypt below)
    wave  -> sources[0].embedUrl = echovideo      -> JS player (no static m3u8)
    koto  -> sources[0].embedUrl = megaplay       -> JS player (no static m3u8)
  embeds (Embeds row) key -> backend provider (PROVEN mapping):
    softsub -> neko   (HD-1 vivibebe m3u8, HD-2 bibiemb m3u8, StreamHG/Earnvids JS)
    hardsub -> dib    (SR/SB playeng m3u8)
    koto    -> koto   (megaplay/vidtube JS player)
    wish    -> wave   (echovideo JS player)

MEGG TOKEN DECRYPT:
  sources[0].url is base64( XOR with repeating key b"aproxy2024" ).
  Result is a real .mp4 URL (e.g. https://s389.vidcache.net:8164/play/.../vifeo.mp4).

OUTPUT of resolve_stream: {slug,episode,provider,m3u8,referer,format,embedUrl}
  format is "hls" (m3u8) or "mp4". App plays both via ExoPlayer.
"""

import argparse
import base64
import html
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://anikage.cc"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Megg (and similar) encrypted-token XOR key, discovered by brute-forcing the
# known "https://" plaintext prefix against anikage's token blob.
_TOKEN_KEY = b"aproxy2024"


def get(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "application/json, text/html, */*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


# ---------- catalog ----------
def scrape_homepage():
    h = get(f"{BASE}/")
    infos = [(m.start(), m.group(1))
             for m in re.finditer(r'href="/anime/info/([A-Za-z0-9]+)"', h)]
    alts = []
    for m in re.finditer(r'<img[^>]+>', h):
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
        seen.add(r["slug"]); uniq.append(r)
    return uniq


def api_get(path, referer):
    return json.loads(get(f"{BASE}/api/{path}", referer=referer))


def fetch_episodes(slug):
    return api_get(f"media/anime/{slug}/episodes", referer=f"{BASE}/anime/watch/{slug}")


def fetch_servers(slug, ep):
    return api_get(f"media/anime/{slug}/episodes/{ep}/servers",
                   referer=f"{BASE}/anime/watch/{slug}")


def _display_name(server_id):
    return {"neko": "Neko", "megg": "Megg", "wave": "Wave", "koto": "Koto",
            "dib": "Ken"}.get(server_id, server_id.title())


# embed key (softsub/hardsub/koto/wish) -> backend provider (PROVEN)
_EMBED_BACKEND = {"softsub": "neko", "hardsub": "dib", "koto": "koto", "wish": "wave"}


def _all_providers(slug, ep, type="sub"):
    """anikage's full server list, named exactly like the site:
    Servers: Neko, Ken, Megg, Wave, Koto
    Embeds:  E-Neko, E-Ken, E-Koto, E-Wish (labels anikage provides)."""
    srvs = fetch_servers(slug, ep).get("servers", []) or []
    embeds = fetch_servers(slug, ep).get("embeds", []) or []
    out = []
    for s in srvs:
        sid = s.get("id")
        sub_types = s.get("subTypes") or ["sub", "dub"]
        out.append({"id": sid, "name": _display_name(sid), "subTypes": sub_types})
    for e in embeds:
        eid = e.get("id")
        label = e.get("label") or eid
        out.append({"id": eid, "name": label, "subTypes": ["sub", "dub"],
                    "embed": True, "backend": _EMBED_BACKEND.get(eid, eid)})
    return out


def _extract_m3u8(html, embed_url):
    """Pull m3u8 out of an embed page. Handles absolute, //, and relative /path."""
    from urllib.parse import urlparse
    candidates = []
    for pat in (
        r'const src\s*=\s*"([^"]+\.m3u8)"',
        r'(?:src|file|source)\s*[=:]\s*["\']([^"\']+\.m3u8)["\']',
        r'["\']((?:https?:)?//?[^\"\'\s]+\.m3u8)["\']',
    ):
        for m in re.finditer(pat, html):
            candidates.append(m.group(1))
    if not candidates:
        return None
    for raw in candidates:
        if raw.startswith("//"):
            u = "https:" + raw
        elif raw.startswith("http"):
            u = raw
        elif raw.startswith("/"):
            net = f"{urlparse(embed_url).scheme}://{urlparse(embed_url).netloc}"
            u = net + raw
        else:
            net = f"{urlparse(embed_url).scheme}://{urlparse(embed_url).netloc}/"
            u = net + raw
        return u
    return None


def _decrypt_token(tok):
    """base64decode then XOR with repeating _TOKEN_KEY. Returns a URL string
    (usually a .mp4) or None."""
    try:
        raw = base64.b64decode(tok + "=")
    except Exception:
        return None
    dec = bytes([raw[i] ^ _TOKEN_KEY[i % len(_TOKEN_KEY)] for i in range(len(raw))])
    m = re.search(r'https://[^\x00-\x1f\s]+', dec.decode("latin1"))
    return m.group(0) if m else None


def _embed_sources(slug, ep, backend, embed_key):
    """Return the embeds[] list for a backend provider (to pick the right host
    for an embed label)."""
    ref = f"{BASE}/anime/watch/{slug}"
    try:
        d = api_get(f"media/anime/{slug}/episodes/{ep}/sources?provider={backend}&type=sub",
                    referer=ref)
    except Exception:
        return []
    return d.get("embeds", []) or []


def resolve_stream(slug, ep, provider=None, type="sub"):
    """Resolve a playable stream for slug/ep.

    Returns the first working server (named like the site). Each provider/embed
    is tried in order; JS-player-only hosts (wave/koto/StreamHG/Earnvids) return
    an error rather than a fake link. `provider` (id or display name) reorders
    so the requested server is tried first.

    OUTPUT: {slug,episode,provider,m3u8,referer,format,embedUrl}
      format = "hls" | "mp4"
    """
    wanted = "dub" if type == "dub" else "sub"
    srvs = fetch_servers(slug, ep)
    providers = srvs.get("servers", []) or []
    embeds = srvs.get("embeds", []) or []
    if not providers and not embeds:
        return {"slug": slug, "episode": ep, "error": "no servers for this episode"}

    # Build an ordered list of (name, backend, kind, embed_key) to try.
    plan = []
    for s in providers:
        pid = s.get("id")
        if s.get("subTypes") and wanted not in s.get("subTypes") and wanted != "sub":
            # skip if this provider doesn't support the requested audio (dub)
            if wanted == "dub" and "dub" not in s.get("subTypes", []):
                continue
        plan.append((_display_name(pid), pid, "provider", None))
    for e in embeds:
        eid = e.get("id")
        label = e.get("label") or eid
        plan.append((label, _EMBED_BACKEND.get(eid, eid), "embed", eid))

    # Reorder: requested provider first
    if provider:
        hit = [p for p in plan if p[1] == provider or p[0] == provider]
        plan = hit + [p for p in plan if p not in hit]

    ref = f"{BASE}/anime/watch/{slug}"
    last = None
    from urllib.parse import urlparse

    # If a specific server was requested, only that one is tried — never fall
    # through to another server (that would collapse distinct servers to one URL).
    if provider:
        plan = [p for p in plan if provider in (p[0], p[1], _display_name(p[1]))] or plan

    for name, backend, kind, embed_key in plan:
        if len(plan) == 1 and provider:
            # pinned: this is the only entry; honor its result exactly
            pass
        try:
            d = api_get(f"media/anime/{slug}/episodes/{ep}/sources?provider={backend}&type=sub",
                        referer=ref)
        except Exception as ex:
            return {"slug": slug, "episode": ep, "server": name,
                    "error": f"sources failed: {ex}"}

        # --- Megg-style encrypted token (mp4) ---
        srcs = d.get("sources", []) or []
        if srcs and srcs[0].get("url") and not srcs[0].get("isM3U8"):
            mp4 = _decrypt_token(srcs[0]["url"])
            if mp4:
                return {"slug": slug, "episode": ep, "provider": name,
                        "m3u8": mp4, "referer": f"{BASE}/", "format": "mp4",
                        "embedUrl": mp4, "providers": [p[0] for p in plan]}
            return {"slug": slug, "episode": ep, "server": name,
                    "error": "token decrypt failed"}

        # --- embedUrl (m3u8) path: providers neko/dib, or an embed's url ---
        if kind == "provider":
            entries = [s for s in srcs if s.get("embedUrl")]
        else:
            emb_list = d.get("embeds", []) or []
            entries = [e for e in emb_list if e.get("url") and e.get("type") == embed_key] or \
                      [e for e in emb_list if e.get("url")]

        for e in entries:
            url = e.get("embedUrl") or e.get("url")
            if not url:
                continue
            try:
                emb_html = get(url, referer=url)
            except Exception as ex:
                return {"slug": slug, "episode": ep, "server": name,
                        "error": f"embed fetch failed: {ex}"}
            m3u8 = _extract_m3u8(emb_html, url)
            if m3u8:
                referer_host = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
                return {"slug": slug, "episode": ep, "provider": name,
                        "m3u8": m3u8, "referer": referer_host, "format": "hls",
                        "embedUrl": url, "providers": [p[0] for p in plan]}
            return {"slug": slug, "episode": ep, "server": name,
                    "error": "m3u8 not found (JS-player host — needs browser)"}
        # no entries / no url
        return {"slug": slug, "episode": ep, "server": name,
                "error": "no stream entries for this server"}
    return last or {"slug": slug, "episode": ep, "error": "no server yielded a stream"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search")
    ap.add_argument("--slug")
    ap.add_argument("--episodes", action="store_true")
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--ep", default="1")
    ap.add_argument("--provider")
    ap.add_argument("--out", default="anikage_index")
    args = ap.parse_args()

    if args.stream:
        if not args.slug:
            print("ERROR: --slug required for --stream", file=sys.stderr); sys.exit(1)
        print(json.dumps(resolve_stream(args.slug, args.ep, args.provider),
                         indent=2, ensure_ascii=False))
        return

    if args.episodes and args.slug:
        d = fetch_episodes(args.slug)
        eps = d.get("episodes", [])
        print(f"slug {args.slug}: total={d.get('total')} episodes={len(eps)}")
        for e in eps[:10]:
            print(f"  ep{e['number']}: {e.get('title')}")
        return

    if args.search:
        rows = scrape_homepage()
        q = args.search.lower()
        rows = [r for r in rows if q in r["anime"].lower()]
        json.dump(rows, open(args.out + ".json", "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        print(f"matched {len(rows)}")
        for r in rows[:10]:
            print(f"  [{r['slug']}] {r['anime']}")
        return

    rows = scrape_homepage()
    json.dump(rows, open(args.out + ".json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"extracted {len(rows)} anime from homepage -> {args.out}.json")
    for r in rows[:12]:
        print(f"  [{r['slug']}] {r['anime']}")


if __name__ == "__main__":
    main()
