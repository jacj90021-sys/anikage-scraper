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


def _display_name(server_id):
    """Map anikage's server id to the display name shown on the site
    (screenshot: Neko/Ken/Megg/Wave/Koto). 'dib' is aliased to 'Ken' in the
    frontend (Je={...,ken:{backend:neko,...}})."""
    return {"neko": "Neko", "megg": "Megg", "wave": "Wave", "koto": "Koto",
            "dib": "Ken"}.get(server_id, server_id.title())


def _provider_sources(slug, ep, pid, wanted):
    """Fetch the working stream entries for one provider (neko/megg/dib/wave/koto).
    anikage's /sources?provider=<pid>&type=<type> returns a `sources` array where
    each entry has an `embedUrl` (a real, working host) + a `type` (softsub/hardsub/
    embed). We select entries matching the requested audio type. This is the
    reliable path — these embedUrls actually resolve (vivibebe, playeng,
    echovideo, megaplay, vidtube). Returns list of {url, type, host}."""
    ref = f"{BASE}/anime/watch/{slug}"
    src = api_get(f"media/anime/{slug}/episodes/{ep}/sources?provider={pid}&type={wanted}",
                  referer=ref)
    out = []
    for s in (src.get("sources", []) or []):
        eu = s.get("embedUrl")
        if not eu:
            continue
        out.append({"url": eu, "type": s.get("type", wanted), "host": eu.split("/")[2]})
    return out


def _all_providers(slug, ep, type="sub"):
    """anikage's REAL server list, named exactly like the site:
    Neko, Ken, Megg, Wave, Koto (one row per provider, plus each provider's
    extra host entries). Each carries the audio types it supports."""
    wanted = "dub" if type == "dub" else "sub"
    srvs = fetch_servers(slug, ep).get("servers", []) or []
    out = []
    for s in srvs:
        sid = s.get("id")
        sub_types = s.get("subTypes") or (["sub", "dub"] if wanted in ("sub", "dub") else [wanted])
        out.append({"id": sid, "name": _display_name(sid),
                    "subTypes": sub_types})
    return out


def resolve_stream(slug, ep, provider=None, type="sub"):
    """Resolve an m3u8 for a slug/ep using anikage's REAL working servers.

    Strategy (the reliable one): iterate anikage's providers (neko/megg/dib/wave/
    koto), fetch each via /sources?provider=<pid>&type=<type>, take the entry
    whose `type` matches the requested audio (softsub=sub, hardsub=dub), use its
    `embedUrl` (a real host: vivibebe/playeng/echovideo/megaplay/vidtube), fetch
    the embed page, extract the m3u8. Anikage returns MULTIPLE host entries per
    provider (neko -> vivibebe + bibiemb; koto -> megaplay + vidtube), so each
    becomes a selectable server. If a provider/type yields nothing, we move on —
    never silently fake sub for a requested dub."""
    wanted = "dub" if type == "dub" else "sub"
    lang = "dub" if type == "dub" else "sub"
    srvs = fetch_servers(slug, ep).get("servers", []) or []
    if not srvs:
        return {"slug": slug, "episode": ep, "error": "no servers for this episode"}
    # order: requested provider first (by id or display name), then as listed
    order = list(srvs)
    if provider:
        hit = [s for s in srvs if s.get("id") == provider or _display_name(s.get("id")) == provider]
        if hit:
            order = hit + [s for s in srvs if s not in hit]

    last = None
    tried = []
    for s in order:
        pid = s.get("id")
        name = _display_name(pid)
        try:
            entries = _provider_sources(slug, ep, pid, lang)
        except Exception as ex:
            last = {"slug": slug, "episode": ep, "server": name,
                    "error": f"sources failed: {ex}"}
            continue
        if not entries:
            last = {"slug": slug, "episode": ep, "server": name,
                    "error": f"no {wanted} sources for provider"}
            continue
        for e in entries:
            tried.append(f"{name}/{e['host']}")
            try:
                emb_html = get(e["url"], referer=e["url"])
            except Exception as ex:
                last = {"slug": slug, "episode": ep, "server": name,
                        "error": f"embed fetch failed: {ex}"}
                continue
            m3u8 = _extract_m3u8(emb_html, e["url"])
            if m3u8:
                from urllib.parse import urlparse
                referer_host = f"{urlparse(e['url']).scheme}://{urlparse(e['url']).netloc}/"
                return {
                    "slug": slug, "episode": ep, "provider": name,
                    "providers": [x["name"] for x in order],
                    "embedUrl": e["url"], "m3u8": m3u8, "referer": referer_host,
                }
            last = {"slug": slug, "episode": ep, "server": name,
                    "error": "m3u8 not found in embed page"}
    return last or {"slug": slug, "episode": ep, "error": "no server yielded m3u8"}


# ---------- stream ----------
def _extract_m3u8(html, embed_url):
    """Pull the m3u8 URL out of an anikage embed page. Tries several patterns:
    `const src="...m3u8"`, any src/file/source attr with an m3u8, a bare
    https m3u8, and a *relative* /path.m3u8 (anikage's playeng host uses this).
    Relative paths are resolved against the embed page's origin."""
    from urllib.parse import urlparse
    candidates = []
    for pat in (
        r'const src\s*=\s*"([^"]+\.m3u8)"',
        r'(?:src|file|source)\s*[=:]\s*["\']([^"\']+\.m3u8)["\']',
        r'["\']((?:https?:)?//?[^"\'\s]+\.m3u8)["\']',
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
            # relative without leading slash
            net = f"{urlparse(embed_url).scheme}://{urlparse(embed_url).netloc}/"
            u = net + raw
        return u
    return None


def _display_name(server_id):
    """Map anikage's server id to the display name shown on the site
    (screenshot: Neko/Ken/Megg/Wave/Koto). 'dib' is aliased to 'Ken' in the
    frontend (Je={...,ken:{backend:neko,...}})."""
    return {"neko": "Neko", "megg": "Megg", "wave": "Wave", "koto": "Koto",
            "dib": "Ken"}.get(server_id, server_id.title())


# anikage embed id -> (backend provider, display label) per frontend mapping
# vt={softsub:neko, hardsub:neko, koto:koto, wish:koto}; labels from servers embeds
_EMBED_LABELS = {"softsub": "E-Neko", "hardsub": "E-Ken", "koto": "E-Koto", "wish": "E-Wish"}
_EMBED_BACKEND = {"softsub": "neko", "hardsub": "neko", "koto": "koto", "wish": "koto"}


def _embed_servers(slug, ep, lang):
    """anikage's REAL server list, named exactly like the site.

    Two groups (matches the anikage watch UI):
      * Servers: Neko, Ken, Megg, Wave, Koto  (from the `servers` API ids)
      * Embeds:  E-Neko, E-Ken, E-Koto, E-Wish (from the `servers` API embeds,
                 each with a `label` anikage itself provides)

    We return a unified list of {id, name, backend, embed_id, type} so the
    resolver can fetch the right stream while the UI shows the site's names.
    anikage's `lang` param is unreliable (lang=dub returns empty), so we always
    fetch lang=sub and select by the embed `type` (softsub=sub, hardsub=dub)."""
    ref = f"{BASE}/anime/watch/{slug}"
    srvs = fetch_servers(slug, ep)
    out = []
    # Servers row (Neko/Ken/Megg/Wave/Koto) — each is a provider selector.
    for s in (srvs.get("servers", []) or []):
        sid = s.get("id")
        out.append({"id": sid, "name": _display_name(sid), "backend": sid,
                    "embed_id": None, "type": "softsub"})
    # Embeds row (E-Neko/E-Ken/E-Koto/E-Wish) — anikage gives the label.
    for e in (srvs.get("embeds", []) or []):
        eid = e.get("id")  # softsub/hardsub/koto/wish
        label = e.get("label") or _EMBED_LABELS.get(eid, eid)
        out.append({"id": eid, "name": label, "backend": _EMBED_BACKEND.get(eid, eid),
                    "embed_id": eid, "type": "hardsub" if eid == "hardsub" else "softsub"})
    return out


def _embed_url(slug, ep, backend, embed_id, wanted_type):
    """Fetch the real stream url for a (backend, embed_id) pair. The sources
    response's `embeds` array carries {url, server, type}; we pick the entry
    matching the requested embed_id (or type when embed_id is None)."""
    ref = f"{BASE}/anime/watch/{slug}"
    src = api_get(f"media/anime/{slug}/episodes/{ep}/sources?provider={backend}&lang=sub",
                  referer=ref)
    embeds = src.get("embeds", []) or []
    if not embeds:
        s0 = (src.get("sources") or [])
        if s0 and s0[0].get("embedUrl"):
            return [{"url": s0[0]["embedUrl"], "server": "default", "type": "softsub"}]
    # pick by embed_id (softsub/hardsub/koto/wish) if given, else by type
    if embed_id:
        match = [e for e in embeds if e.get("type") == embed_id]
        if not match:
            match = embeds
    else:
        match = [e for e in embeds if e.get("type") == wanted_type] or embeds
    return match


def resolve_stream(slug, ep, provider=None, type="sub"):
    """Resolve an m3u8 for a slug/ep using anikage's REAL named servers.
    `type` is 'sub' or 'dub'. Returns the first working server, named exactly
    like the site (Neko/Ken/.../E-Neko/...). If the requested audio type has no
    server, returns a clean error — never a silent fallback."""
    wanted = "hardsub" if type == "dub" else "softsub"
    servers = _embed_servers(slug, ep, type)
    if not servers:
        return {"slug": slug, "episode": ep, "error": "no servers for this episode"}
    # only servers that can serve the requested audio type
    typed = [s for s in servers if s["type"] == wanted or s["embed_id"] is None]
    if not typed:
        return {"slug": slug, "episode": ep,
                "error": f"no {type} server for this episode",
                "providers": [s["name"] for s in servers]}
    # order: requested provider (by id or display name) first
    order = []
    if provider:
        order += [s for s in typed if s["id"] == provider or s["name"] == provider]
    order += [s for s in typed if s not in order]

    ref = f"{BASE}/anime/watch/{slug}"
    last = None
    for s in order:
        try:
            embeds = _embed_url(slug, ep, s["backend"], s["embed_id"], wanted)
        except Exception as ex:
            last = {"slug": slug, "episode": ep, "server": s["name"],
                    "error": f"sources failed: {ex}"}
            continue
        for e in embeds:
            url = e.get("url")
            if not url:
                continue
            try:
                emb_html = get(url, referer=url)
            except Exception as ex:
                last = {"slug": slug, "episode": ep, "server": s["name"],
                        "error": f"embed fetch failed: {ex}"}
                continue
            m3u8 = _extract_m3u8(emb_html, url)
            if m3u8:
                from urllib.parse import urlparse
                referer_host = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
                return {
                    "slug": slug, "episode": ep, "provider": s["name"],
                    "providers": [x["name"] for x in servers],
                    "embedUrl": url, "m3u8": m3u8, "referer": referer_host,
                }
            last = {"slug": slug, "episode": ep, "server": s["name"],
                    "error": "m3u8 not found in embed page"}
    return last or {"slug": slug, "episode": ep, "error": "no server yielded m3u8"}


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
