# anime-stream-scraping-playbook

A **field manual** for scraping playable anime streams (real `m3u8` / `mp4` + the
required `Referer` + subtitles) from anime aggregator sites, built from real
reverse-engineering work — not theory.

The goal: let **another AI (or you)** take these methods and apply them to **any**
anime site, because the techniques below are site-agnostic patterns. Each site just
wraps one or more of these patterns differently.

## How to use this repo

1. Read `METHODS.md` — the A→Z catalog of techniques. Each method says:
   - When to try it
   - The exact mechanism
   - The failure mode (what "broken" looks like)
2. Read `sites/*.md` — concrete worked examples (just4anime, anikage, otakuhg,
   animegg, megaplay, vivibebe, prox.anicore). These are the proof the methods work.
3. Copy a template from `templates/` and adapt.
4. `methods.json` — machine-readable index if you want to feed this to an agent
   programmatically.
5. `pitfalls.md` — the mistakes that cost the most time. Read before you start.

## The golden rules (non-negotiable)

- **A proxy path is NEVER the real URL.** `cors.site.com/proxy/e/<token>` is a
  server-side fetch wrapper. You must resolve it to the upstream CDN `m3u8` OR confirm
  the proxy itself returns a valid playlist with the right referer. Never assert a
  stream "works" from reading code — fetch it and get HTTP 200 + valid `#EXTM3U`.
- **Verify every claim with a real fetch.** 200 + valid HLS body + a segment that
  downloads. Anything less is unproven.
- **Referer is mandatory on SEGMENTS, not just the master.** A 200 on the master but
  404 on segments = wrong/missing referer.
- **Upstream metadata lies.** `episode.id` / titles from the API are often wrong
  (we saw Black Clover → "Your Name"). Trust the resolved stream URL + on-device
  playback, not the label.
- **Don't drop a server — find a different method.** "Browser-only" usually means
  "you didn't decode the client JS yet." (otakuhg was "browser-only" until we ran
  its packed script in node.)

## What's in here

| File | Purpose |
|------|---------|
| `METHODS.md` | A→Z technique catalog |
| `methods.json` | Machine-readable index of methods + sites |
| `sites/*.md` | Per-site worked examples |
| `templates/` | Reusable, working code (node decoder, HLS fetch, embed extract, Flask API) |
| `pitfalls.md` | Costly mistakes + how to avoid them |
