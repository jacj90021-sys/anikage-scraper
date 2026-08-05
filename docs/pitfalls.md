# pitfalls.md — the mistakes that cost the most time

Read this before you start. Every one below was hit in real reverse-engineering.

## P1. Trusting a proxy path as the real URL
`cors.site.com/proxy/e/<token>` is NOT a stream. Either (a) confirm it returns a
valid `#EXTM3U` playlist with the right referer, or (b) decode the upstream yourself.
Asserting "it should work" from reading the URL = wrong, every time.

## P2. Asserting a stream works without fetching it
The user will test on-device. If you didn't get HTTP 200 + valid HLS + a downloading
segment, you have NOT verified it. "The code looks fine" is not proof.

## P3. Forgetting the referer on SEGMENTS
Master returns 200, variant returns 200, but segments 404. Cause: referer attached to
master only, not forwarded to segment fetches. The player/CDN requires it on every hop.
Fix: attach referer at the HTTP-data-source level so it follows redirects + relative
paths. (otakuhg: segments 404 without `https://otakuhg.site/`.)

## P4. Relative subtitle URL → host-less Uri → silent no-subs
ExoPlayer needs an ABSOLUTE subtitle URL. A relative `/api/proxy?...` builds a Uri with
no host → silent failure (no crash, no subs). Fix: absolutize against the backend BASE,
and use 2-letter lang codes (`en` not `eng`) so TrackSelector matches.

## P5. Trusting upstream `episode.id` / titles
Aggregator metadata lies. just4anime's ryuk returned `kimi-no-na-wa-episode-1` (Your
Name) for Black Clover. Always prefer the resolved stream URL + on-device check.

## P6. Re-deriving a CDN's id from the anilist id
megaplay's id space ≠ anilist. `getSources?id=<anilistId>` returns the wrong anime.
Trust the aggregator's already-resolved URL instead of re-deriving.

## P7. "Browser-only" = you didn't decode the client JS
otakuhg was declared browser-only for weeks. It was a packed jwplayer — 10 lines of
node decode solved it. Before dropping a server, run its client script in node (M3).

## P8. Chromium hangs in sandboxes
A headless browser is the heavy fallback. In restricted environments it may hang/block.
Prefer node-decode (M3) or literal extraction (M2) — they need no browser.

## P9. Ignoring typed mirror tabs
animegg/otakuhg pages have raw/sub/dub mirrors. Grabbing the first embed ignores the
user's sub/dub choice. Parse `data-version` and match the requested type.

## P10. Not binding $PORT on Render
Hardcoding `port=3000` makes the deploy fail (Render injects $PORT). Always
`port=int(os.environ.get("PORT", 3000))`.

## P11. Exposing credentials
GitHub PATs / API keys pasted in chat or committed = compromised. Redact to [REDACTED]
and rotate immediately at the provider's token page.

## P12. Pushing without explicit go-ahead
The user owns the repos/deploys. Present code + verification freely, but STOP before
any push/deploy/revert. Wait for "yes".
