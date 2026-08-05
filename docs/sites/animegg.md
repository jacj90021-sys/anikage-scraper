# Site: animegg.org

The real video host behind just4anime's `ryuk` server (and many other aggregators).
Serves both HLS (via embed pages) and direct MP4.

## Episode pages have TYPED MIRROR TABS
`https://www.animegg.org/<slug>-episode-<N>` contains multiple mirrors:
```
data-id="88495" data-mirror="Animegg" data-version="raw"
data-id="88522" data-mirror="Animegg" data-version="subbed"
data-id="134379" data-mirror="Animegg" data-version="dubbed"
```
Each `embed/<id>` → `play/<id>/video.mp4?for=<token>`.

**Pick the mirror whose `data-version` matches the requested type** (raw/subbed/dubbed).
Ignoring this returns a random/untyped embed (wrong sub/dub choice).

## MP4 delivery (M5)
`play/<id>/video.mp4` 302-redirects to `vidcache.net/play/<token>/video.mp4`.
- **Referer `https://animegg.org/` is mandatory.** Without it the CDN connection fails
  (000). vidcache URLs are per-request tokens — you can't hardcode them; always go
  through `play/<id>/video.mp4` with the referer.

## Slug formats
- Base: `/black-clover-episode-1` (often a single untyped embed)
- Typed: `/black-clover-tv-episode-1` (raw/sub/dub tabs) ← prefer this
- Try `-tv` first when resolving by title.

## Gotcha: aggregator mislabels
just4anime's ryuk returned `play/172230` for Black Clover = **Your Name** (its DB maps
Black Clover→Your Name). The animegg page itself is correct. Resolve from animegg
directly (M4), don't trust the aggregator's ryuk URL.

## Verified
Black Clover ep1: raw `play/188603`, sub `play/188693`, dub `play/468039` — all correct
Black Clover, distinct from just4anime's broken `play/172230`.
