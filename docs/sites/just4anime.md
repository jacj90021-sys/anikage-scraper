# Site: just4anime.online

Aggregator. API: `https://api.just4anime.online/api/v1/meta/sources/<anilistId>?provider=<srv>&num=<ep>&type=<sub|dub|hsub>`

Returns `sources[0].url` (often a cors proxy) + `iframe` list + `subtitles` + `episode.id`.

## Servers & how each is resolved

| Server | Method | Real source | Referer | Status |
|--------|--------|-------------|---------|--------|
| `kai`  | M2 (embed) | vivibebe.site `/public/stream/<id>/master.m3u8` | vivibebe.site | ✅ works |
| `zeke` | M2 (embed) | bibiemb.xyz / vibevibe.workers.dev | host | ✅ works |
| `jin`  | M1 (proxy) | megaplay (`megap.akirax.buzz` / `megap.shiora.top`) | megaplay.buzz | ✅ works (Cloudflare risk) |
| `ryuk` | M4 (self-resolve) | animegg.org typed mirrors | animegg.org | ✅ works (bypasses broken upstream) |
| `sai`  | M3 (node-decode) | otakuhg.site → random `*.site` CDN | otakuhg.site | ✅ works |
| `mai`  | M3 (node-decode) | otakuhg.site → random `*.space` CDN | otakuhg.site | ✅ works |
| `echo` | — | just4anime encrypted Cloudflare proxy | — | ❌ not resolvable server-side |

## Key lessons
- **kai/zeke:** the m3u8 is a literal string in the iframe page JS. Extract + use the
  iframe host as referer. Sub and dub share the same vivibebe stream id (dub audio is
  an in-player track).
- **jin:** DO NOT re-resolve megaplay with the anilist id — that produced a
  WRONG-ANIME bug. Use just4anime's own `sources[0].url` (it resolved megaplay's id
  server-side). The master.m3u8 has multiple RESOLUTION variants (ExoPlayer shows a
  quality menu; the site hides it — that's normal, not a borrowed stream).
- **ryuk:** just4anime's own ryuk→animegg mapping is MISLABELED for some shows
  (Black Clover ep1 → "Your Name" movie, `play/172230`). Resolve from animegg yourself
  (M4) using the animegg `-tv` page's typed mirror tabs (raw/sub/dub). Match the type.
- **sai/mai:** otakuhg.site. The iframe is a packed jwplayer (M3). Node-decode → real
  `master.txt` on a random CDN. Referer `https://otakuhg.site/` is REQUIRED (segments
  404 without it). Verified full chain: master → variant → segment (`video/MP2T`, 292KB).
- **echo:** dead end server-side. just4anime's proxy returns "Invalid URL after
  decoding". Browser-only; skip it.

## Subtitles
jin/sub: EN/ID/TH VTT. kai/zeke: EN. sai/mai: dub has EN. ryuk: none. Proxy them
same-origin (M7).
