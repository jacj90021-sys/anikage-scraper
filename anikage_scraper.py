#!/usr/bin/env python3
"""
anikage.cc scraper  (functional — real JSON data layer + m3u8 resolver)
========================================================================

anikage.cc is a SvelteKit anime aggregator. Two layers, both reverse-engineered:

1) CATALOG (server-rendered HTML + JSON API)
   - Homepage https://anikage.cc/ is SSR: anime cards carry
     `/anime/info/<slug>` + cover `<img alt="TITLE">`. Extract slug<->title there.
   - Episodes + server list come from a clean JSON API (no bot-check, just a Referer):
       GET /api/media/anime/<slug>/episodes
            -> {"anilistId":..,"total":N,"episodes":[{number,title,...}]}
       GET /api/media/anime/<slug>/episodes/<n>/servers
            -> {"servers":[{id,default,label,subTypes}],"embeds":[...]}

2) STREAM RESOLVER
   The /sources endpoint returns OBFUSCATED data:
       GET /api/media/anime/<slug>/episodes/<n>/sources?provider=<serverId>
            -> {"sources":[{"url":"<encrypted-blob>","isM3U8":true,
                             "embedUrl":"https://<host>/<id>"}]}
   The `url` blob is NOT a real m3u8 — it's decoded only by the embed iframe's JS.
   The REAL m3u8 is hardcoded inside the embed page's inline script:
       fetch embedUrl  ->  inline JS contains  const src = "https://<host>/public/stream/<id>/master.m3u8"
   So: take `embedUrl` from the sources response, fetch that HTML, regex the
   `master.m3u8` out of the inline player setup. That URL is the genuine, playable
   HLS stream (needs the embed host as Referer, same as anidap).

USAGE
  index:
    python3 anikage_scraper.py                 # recents from homepage
    python3 anikage_scraper.py --search "frieren"
    python3 anikage_scraper.py --slug 3VNfCE9Yt7 --episodes   # episode list for a slug

  stream (m3u8):
    python3 anikage_scraper.py --stream --slug 3VNfCE9Yt7 --ep 1
    python3 anikage_scraper.py --stream --slug 3VNfCE9Yt7 --ep 1 --provider neko

OUTPUT per stream: {slug,episode,provider,embedUrl,m3u8,referer}

COPYRIGHT: resolves the player's own stream URL (what the site's video player
loads). No downloader / segment merger included (would facilitate copying
unlicensed video). Use the m3u8 with the required Referer in a normal HLS player
or via anikage's own player.
"""
import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://anikage.cc"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


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
    # collect cover-img alts with positions (handle both attr orders)
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
    d = api_get(f"media/anime/{slug}/episodes", referer=f"{BASE}/anime/watch/{slug}")
    return d


def fetch_servers(slug, ep):
    d = api_get(f"media/anime/{slug}/episodes/{ep}/servers",
                referer=f"{BASE}/anime/watch/{slug}")
    return d


# ---------- stream ----------
def resolve_stream(slug, ep, provider=None, type="sub"):
    """Resolve an m3u8 for a slug/ep. `type` is 'sub' or 'dub' — anikage's
    sources endpoint takes &type= and returns empty when that type is missing
    for the episode, so callers must surface the failure instead of faking sub."""
    ref = f"{BASE}/anime/watch/{slug}"
    servers = fetch_servers(slug, ep)
    srvs = servers.get("servers", [])
    if not srvs:
        return {"slug": slug, "episode": ep, "error": "no servers",
                "raw": servers}
    # Only consider providers that actually support the requested audio type.
    # anikage reports subTypes per provider; a provider without the requested type
    # (e.g. "dub") MUST NOT be used, or we'd silently play sub / a wrong source.
    wanted = type if type in ("sub", "dub") else "sub"
    type_ok = [s for s in srvs if wanted in (s.get("subTypes") or [])]
    if not type_ok:
        return {"slug": slug, "episode": ep, "error": f"no {wanted} provider for this episode",
                "providers": [s["id"] for s in srvs]}
    # resolve one provider at a time; prefer the requested/default, but fall back
    # to the first provider (of the type-compatible set) whose embed exposes m3u8.
    order = []
    if provider:
        order.append(next((s for s in type_ok if s["id"] == provider), None))
    order.append(next((s for s in type_ok if s.get("default")), None))
    order += [s for s in type_ok if s not in order]
    order = [s for s in order if s]

    last = None
    for s in order:
        pid = s["id"]
        try:
            src = api_get(f"media/anime/{slug}/episodes/{ep}/sources?provider={pid}&type={type}",
                          referer=ref)
        except Exception as e:
            last = {"slug": slug, "episode": ep, "provider": pid,
                    "error": f"sources call failed: {e}"}
            continue
        embeds = src.get("sources", [])
        if not embeds:
            last = {"slug": slug, "episode": ep, "provider": pid,
                    "error": "no sources", "raw": src}
            continue
        embed_url = embeds[0].get("embedUrl", "")
        if not embed_url:
            last = {"slug": slug, "episode": ep, "provider": pid,
                    "encrypted_url": embeds[0].get("url"),
                    "error": "no embedUrl in source"}
            continue
        emb_html = get(embed_url, referer=embed_url)
        m = re.search(r'const src\s*=\s*"([^"]+\.m3u8)"', emb_html)
        if not m:
            m = re.search(r'(https?://[^\s"\']+\.m3u8|/[^\s"\']+\.m3u8)', emb_html)
        m3u8 = None
        if m:
            u = m.group(1)
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                from urllib.parse import urlparse
                net = f"{urlparse(embed_url).scheme}://{urlparse(embed_url).netloc}"
                u = net + u
            m3u8 = u
        if m3u8:
            from urllib.parse import urlparse
            referer_host = (f"{urlparse(embed_url).scheme}://"
                            f"{urlparse(embed_url).netloc}/")
            return {
                "slug": slug, "episode": ep, "provider": pid,
                "providers": [s["id"] for s in srvs],
                "embedUrl": embed_url, "m3u8": m3u8, "referer": referer_host,
            }
        last = {"slug": slug, "episode": ep, "provider": pid,
                "embedUrl": embed_url, "error": "m3u8 not found in embed page"}
    return last or {"slug": slug, "episode": ep, "error": "no provider yielded m3u8"}


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
        # anikage search is SSR too; reuse homepage scrape + filter
        rows = scrape_homepage()
        q = args.search.lower()
        rows = [r for r in rows if q in r["anime"].lower()]
        json.dump(rows, open(args.out + ".json", "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        print(f"matched {len(rows)} (search is client-side filter on homepage)")
        for r in rows[:10]:
            print(f"  [{r['slug']}] {r['anime']}")
        return

    # default: homepage recents
    rows = scrape_homepage()
    json.dump(rows, open(args.out + ".json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"extracted {len(rows)} anime from homepage -> {args.out}.json")
    for r in rows[:12]:
        print(f"  [{r['slug']}] {r['anime']}")


if __name__ == "__main__":
    main()
