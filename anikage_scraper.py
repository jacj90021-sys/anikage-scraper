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


def _all_providers(slug, ep, type="sub"):
    """The real server list anikage exposes is the `embeds` array of the
    sources response (HD-1 vivibebe, HD-2 bibiemb, StreamHG, Earnvids,
    Doodstream, ... each as softsub/hardsub). Return unified provider dicts
    tagged with the audio type each supports, so the UI can list + filter them."""
    embeds = _embed_servers(slug, ep, type)
    out = []
    for e in embeds:
        srv = e.get("server") or e.get("url")
        etype = "dub" if e.get("type") == "hardsub" else "sub"
        out.append({"id": srv, "default": False, "subTypes": [etype], "label": srv})
    return out


# ---------- stream ----------
def _extract_m3u8(html, embed_url):
    """Pull the m3u8 URL out of an anikage embed page. Tries the common
    `const src="...m3u8"` pattern first, then any .m3u8-looking URL."""
    m = re.search(r'const src\s*=\s*"([^"]+\.m3u8)"', html)
    if not m:
        m = re.search(r'(?:src|file|source)\s*[=:]\s*["\']?(https?://[^"\'\s]+?\.m3u8)', html)
    if not m:
        m = re.search(r'(https?://[^"\'\s]+?\.m3u8)', html)
    if not m:
        return None
    u = m.group(1)
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        from urllib.parse import urlparse
        net = f"{urlparse(embed_url).scheme}://{urlparse(embed_url).netloc}"
        u = net + u
    return u


def _embed_servers(slug, ep, lang):
    """anikage's real server list lives in the `embeds` array of the sources
    response (HD-1 vivibebe, HD-2 bibiemb, StreamHG, Earnvids, Doodstream, ...
    each tagged type 'softsub' or 'hardsub'). anikage's `lang` param is unreliable
    (lang=dub returns empty, lang=sub returns BOTH softsub+hardsub), so we always
    fetch lang=sub to get the full embed list, then filter by the `type` field:
    softsub -> sub, hardsub -> dub."""
    ref = f"{BASE}/anime/watch/{slug}"
    src = api_get(f"media/anime/{slug}/episodes/{ep}/sources?provider=neko&lang=sub",
                  referer=ref)
    embeds = src.get("embeds", []) or []
    if not embeds:
        s0 = (src.get("sources") or [])
        if s0 and s0[0].get("embedUrl"):
            embeds = [{"url": s0[0]["embedUrl"], "server": "default", "type": "softsub"}]
    return embeds


def resolve_stream(slug, ep, provider=None, type="sub"):
    """Resolve an m3u8 for a slug/ep. `type` is 'sub' or 'dub'. anikage exposes
    its REAL multi-server list under the sources response's `embeds` array (not
    the single `sources[0].embedUrl` the old code used). We enumerate every
    embed server, pick the requested audio type, and return the first one whose
    embed page yields a playable m3u8. If the requested type (e.g. dub) has no
    embed, we return a clean error — never a silent sub fallback."""
    wanted = "hardsub" if type == "dub" else "softsub"
    embeds = _embed_servers(slug, ep, type)
    if not embeds:
        return {"slug": slug, "episode": ep, "error": "no embeds for this episode"}
    # filter by requested audio type
    typed = [e for e in embeds if e.get("type") == wanted]
    if not typed:
        return {"slug": slug, "episode": ep,
                "error": f"no {type} (embed type {wanted}) server for this episode",
                "providers": [e.get("server") for e in embeds]}
    # order: requested provider first, then as listed
    order = []
    if provider:
        order += [e for e in typed if e.get("server") == provider]
    order += [e for e in typed if e not in order]

    ref = f"{BASE}/anime/watch/{slug}"
    last = None
    for e in order:
        url = e.get("url")
        if not url:
            continue
        try:
            emb_html = get(url, referer=url)
        except Exception as ex:
            last = {"slug": slug, "episode": ep, "server": e.get("server"),
                    "error": f"embed fetch failed: {ex}"}
            continue
        m3u8 = _extract_m3u8(emb_html, url)
        if m3u8:
            from urllib.parse import urlparse
            referer_host = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
            return {
                "slug": slug, "episode": ep, "provider": e.get("server"),
                "providers": [x.get("server") for x in embeds],
                "embedUrl": url, "m3u8": m3u8, "referer": referer_host,
            }
        last = {"slug": slug, "episode": ep, "server": e.get("server"),
                "error": "m3u8 not found in embed page"}
    return last or {"slug": slug, "episode": ep, "error": "no embed server yielded m3u8"}


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
