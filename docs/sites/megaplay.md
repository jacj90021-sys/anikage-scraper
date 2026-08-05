# Site: megaplay (megaplay.buzz / megap.akirax.buzz / megap.shiora.top)

The CDN behind just4anime's `jin` server. The aggregator (just4anime) resolves
megaplay's internal id server-side and returns a cors-proxy URL.

## What we learned (the hard way)
- megaplay exposes `getSources?id=<id>` (AJAX, header `X-Requested-With`). The id space
  is **NOT the anilist id**. Guessing `getSources?id=<anilistId>` returns the WRONG
  anime (we did this once — produced a wrong-anime bug for jin).
- The safe path: use the aggregator's already-resolved `sources[0].url` (it did the
  id mapping for you). That URL points at `megap.akirax.buzz/<hash>/master.m3u8` (sub)
  or `megap.shiora.top/<hash>/master.m3u8` (dub) — distinct hosts per type.
- Referer `https://megaplay.buzz/` required.
- The master.m3u8 has multiple RESOLUTION variants (1080p/720p/360p). ExoPlayer shows
  a quality menu. The just4anime site hides the picker — that's expected, not a sign
  the stream is mislabeled.

## Rule
When an aggregator proxies a CDN that uses its OWN id space, **trust the aggregator's
resolved URL**, don't re-derive the CDN id from the anilist id.
