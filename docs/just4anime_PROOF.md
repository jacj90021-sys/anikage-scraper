# just4anime — VERIFIED PROOF (live check)

This file records an actual live fetch proving the methods in `METHODS.md` work for
just4anime. Re-run `python3 -c "import just4anime_scraper as j; print(j.resolve(...))"`
or hit the deployed `/api/anime/<id>/stream` to reproduce.

## Setup
- Target: just4anime.online, anime anilist `21519` (Black Clover), episode 1.
- Resolver: `just4anime_scraper.resolve(anilist_id, episode, server, typ, title)`.
- Check: `curl -e <referer> -A Mozilla/5.0 <url>` → expect `200` + `application/vnd.apple.mpegurl`.

## Result (fresh live run)

| Server | Type | HTTP | Content-Type | Mechanism (M#) |
|--------|------|------|--------------|----------------|
| kai  | sub | 200 | application/vnd.apple.mpegurl | M2 embed (vivibebe.site) |
| zeke | sub | 200 | application/vnd.apple.mpegurl | M2 embed (bibiemb/vibevibe) |
| jin  | sub | 200 | application/vnd.apple.mpegurl | M1 proxy (megaplay) |
| jin  | dub | 200 | application/vnd.apple.mpegurl | M1 proxy (megaplay) |
| ryuk | sub | 302→200 | video/mp4 (after follow) | M4+M5 (animegg self-resolve) |
| ryuk | dub | 302→200 | video/mp4 (after follow) | M4+M5 (animegg self-resolve) |
| sai  | sub | 200 | application/vnd.apple.mpegurl | M3 node-decode (otakuhg) |
| sai  | dub | 200 | application/vnd.apple.mpegurl | M3 node-decode (otakuhg) |
| mai  | sub | 200 | application/vnd.apple.mpegurl | M3 node-decode (otakuhg) |
| mai  | dub | 200 | application/vnd.apple.mpegurl | M3 node-decode (otakuhg) |

(ryuk shows 302 at the proxy level because the check tool did not follow redirects;
the app/ExoPlayer follows the 302 to `vidcache.net` and gets `200 video/mp4`.)

## Full chain proof — sai/sub (otakuhg, M3)
Decoded via node from `otakuhg.site/e/<id>`:
```
master: https://<rand>.dietandnutritionist.site/<path>/vjugejbr5a21_o/master.txt  (200 HLS)
variant: .../index-v1-a1.txt                                                  (200, 50KB)
segment: .../seg-1-v1-a1.woff2                                                (200 video/MP2T, ~292KB..3.8MB)
referer: https://otakuhg.site/   (without it: 404)
```
Confirmed: master → variant → segment all load. The `.woff2` extension is just
otakuhg's naming; content is MPEG-TS.

## ryuk correctness proof (M4)
just4anime's OWN ryuk for Black Clover ep1 = `play/172230` = **Your Name** (wrong; its
`episode.id` = `kimi-no-na-wa-episode-1`). We resolve from animegg directly:
- sub → `play/188693` (animegg `black-clover-tv-episode-1` subbed mirror)
- dub → `play/468039` (animegg dubbed mirror)
Both are correct Black Clover, distinct from just4anime's broken `play/172230`.

## Servers NOT resolved
- `echo`: just4anime encrypted Cloudflare proxy ("Invalid URL after decoding").
  Browser-only; skipped. No fallback claimed.

## Subtitles (M7)
jin/sub: EN/ID/TH VTT. kai/zeke: EN. sai/mai dub: EN. ryuk: none.
Backend proxies them same-origin so the player isn't CORS-blocked. App absolutizes
the subtitle URL against the backend BASE and uses 2-letter lang (`en`).

## Requirements
- Python 3 + Flask.
- **node** on PATH (for sai/mai M3 decode). Render's Python runtime includes node.
- Bind `$PORT` (Render). Done in `app.py`.
