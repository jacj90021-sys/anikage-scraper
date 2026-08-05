# METHODS.md — the A→Z technique catalog

Each method is a **pattern** you can apply to any anime site. Sites combine these
patterns in different ways. Match the symptom → pick the method.

---

## M1. CORS-proxy passthrough (server-side fetch wrapper)

**Symptom:** API returns a URL like `https://cors.<site>.com/proxy/e/<long-token>`
instead of a bare `m3u8`. This is the site's backend fetching the real stream for
you (to defeat hotlink protection / CORS).

**Mechanism:**
- Just `GET` the proxy URL. Often needs a `Referer` (the site's own origin, or the
  embed host).
- Response is frequently a real HLS playlist (`application/vnd.apple.mpegurl`).
- The playlist's segment lines may be relative (`/proxy/e/<seg>`) — the player (or
  your proxy) resolves them against the cors host, carrying the referer forward.

**Works when:** the site's proxy server is up and not Cloudflare-limiting your IP.
**Breaks when:** the proxy returns `403 ForbiddenError: "Please leave us alone!"`
(intermittent Cloudflare on server IPs). From a user's device it usually works;
from a datacenter it may be rate-limited. **This is a risk, not a guarantee.**

**Verified on:** just4anime `jin` (megaplay-backed), just4anime `sai`/`mai` (otakuhg-
backed) — the proxy URL is the decoded stream; we confirmed 200 + valid HLS.

**Better alternative:** decode the real upstream yourself (see M3/M4) so you don't
depend on the proxy at all.

---

## M2. Embed / iframe m3u8 extraction (literal URL in page JS)

**Symptom:** The API gives an `iframe` URL (`https://<host>/public/stream/<id>` or
`/e/<id>`). Opening it shows a player.

**Mechanism:**
- `GET` the iframe page. The real `m3u8` is often a **literal string in the page's
  JavaScript** (not obfuscated): search for `https://<host>/.../master.m3u8` or
  `file:"..."` / `source:` / `hls`.
- The referer is the iframe host (or its parent).
- Return the literal m3u8 + that referer.

**Works when:** the embed host serves the m3u8 directly (no Cloudflare, no packer).
**Breaks when:** the embed page is itself obfuscated (→ M3) or Cloudflare-locked.

**Verified on:** kai/zeke → `vivibebe.site/public/stream/<id>/master.m3u8`,
`bibiemb.xyz`, `vibevibe.workers.dev`. Literal m3u8 in page JS, referer = embed host.

---

## M3. Node packer-decode (obfuscated jwplayer / eval(p,a,c,k,e,d))

**Symptom:** The player page contains `eval(function(p,a,c,k,e,d){while(c--)if(k[c])...
}('packed',a,c,'k'.split('|')))` — a JavaScript packer (javascriptobfuscator.com
style). The real stream URL is hidden inside, resolved only at runtime in a browser.
Naive regex extraction fails because tokens are base-`a` encoded and the decode is
multi-stage.

**Mechanism (the reliable way — run it, don't reverse it by hand):**
1. Fetch the iframe page.
2. Extract the **balanced-paren** `eval(...)` block (track `(`/`)` depth, ignore
   string literals).
3. Write the block to a `.js` file.
4. Run it in **node** with a hook that captures the player setup call:
   ```js
   global.jwplayer = function(){ return { key:'', setup: function(cfg){
     let s = cfg.sources[0].file; console.log('SETUP_FILE:'+s); } }; };
   global.document = { getElementById: ()=>({}) };
   global.$ = ()=>({});
   try { eval(block); } catch(e){ console.log('ERR:'+e.message); }
   ```
5. Parse `SETUP_FILE:` from stdout → the real m3u8/mp4 (often served with a weird
   extension like `.txt` or `.woff2` — it's still HLS/TS).

**Why node and not a Python regex:** the packer's token scheme is non-trivial
(base-`a` numeric tokens, nested replaces). Running the real decoder is ~10 lines and
always correct. Python `subprocess` → `node` is the bridge.

**Works when:** node is on the host (`shutil.which("node")`). Render's Python runtime
includes node.
**Breaks when:** the page uses WebAssembly or a real browser challenge (rare for
these anime players). If chromium is available, you can also just render and read
`player.getSources()` — but node-decode is lighter.

**Verified on:** otakuhg.site (sai/mai) — decoded `master.txt` on random
`*.site`/`*.space` CDNs. The `Referer` must be `https://otakuhg.site/`.

**Template:** `templates/node_packer_decode.js`

---

## M4. Self-resolution from the real source (bypass a mislabeled upstream)

**Symptom:** The aggregator's API returns a stream URL that plays the **WRONG
anime/episode** (e.g. just4anime's `ryuk` returned "Your Name" for Black Clover).
The aggregator's *database mapping* is corrupt, but the underlying source site is fine.

**Mechanism:**
- Identify the real source the aggregator scrapes from (e.g. `animegg.org`).
- Resolve the correct episode YOURSELF from that source using the anime **title** or
  the source's own slug:
  - Get the series slug (from the title: lowercase + hyphenate; or reuse the
    aggregator's `episode.id` slug when it's valid).
  - Fetch `/<slug>-episode-<N>` on the source.
  - The page exposes **typed mirror tabs** (raw / sub / dub) via `data-version=`
    attributes. Pick the embed matching the requested type.
  - Follow `embed/<id>` → `play/<id>/video.mp4` (302 → CDN). Referer required.
- This bypasses the aggregator entirely for the stream URL.

**Works when:** the source site has stable, crawlable episode pages.
**Breaks when:** the source itself is Cloudflare-locked or the title→slug mapping is
unreliable (romaji slugs). Fallback: try multiple slug variants (`-tv`, `-dub`,
strip colons).

**Verified on:** ryuk → animegg.org. Black Clover ep1: aggregator said `play/172230`
(Your Name); we resolved `play/188693` (sub) / `play/468039` (dub) from animegg's own
typed mirrors. Correct.

---

## M5. Redirect-follow MP4 (single-file, not HLS)

**Symptom:** The stream is a `.mp4`, not an m3u8. The URL is `play/<id>/video.mp4`
that 302-redirects to a CDN (e.g. `vidcache.net`).

**Mechanism:**
- Return the `play/<id>/video.mp4` URL. The player follows the 302.
- **Referer is mandatory** (`https://<source>/`). Without it the CDN returns 000/
  403. The aggregator's API often OMITS this referer — you must hardcode it.
- No quality menu (single file). That's expected.

**Verified on:** animegg/ryuk. Referer `https://animegg.org/` required; 302 →
`vidcache.net`. Without referer: connection fails.

---

## M6. API-contract mirror (so the app doesn't change)

**Symptom:** You have an Android ExoPlayer app that already consumes one backend's
API shape (e.g. anikage-scraper: `/api/anime/<id>/servers`, `/api/anime/<id>/stream`,
`/api/proxy`). You want a NEW scraper to plug in without touching app code.

**Mechanism:** Build a Flask API with the SAME endpoints + response shape:
- `/api/anime/<anilistId>/servers?ep=N` → `{"servers":[{"server","name","types"}]}`
- `/api/anime/<anilistId>/stream?ep=N&server=&type=&title=` →
  `{"url","referer","format","isM3U8","subtitles":[{"file","label"}]}`
- `/api/proxy?url=<vtt>` → same-origin subtitle proxy (text/vtt)
- Bind to `$PORT` (Render requirement — hardcode `port=int(os.environ.get("PORT",3000))`).

**Verified on:** just4anime-scraper mirrors anikage-scraper exactly; the AniwaveStream
app consumes both via the same `Just4animeApi`/`AnikageApi` shape.

**Template:** `templates/flask_api_template.py`

---

## M7. Subtitle handling (the silent ExoPlayer killer)

**Symptom:** Video plays but subtitles don't show, or the app crashes.

**Mechanism:**
- ExoPlayer's `SubtitleConfiguration` / `MediaSource` needs an **absolute** subtitle
  URL. A relative `/api/proxy?...` with no host → host-less `Uri` → **silent failure**.
  You MUST absolutize against the backend base URL.
- The language code must match what `TrackSelector` prefers. Many apps use **2-letter**
  codes (`en`, `id`, `th`), not `eng`/`ind`/`tha`. Map the source's lang to 2-letter.
- Proxy subtitles same-origin (the backend fetches the `.vtt` and returns it) so the
  player isn't blocked by the subtitle host's CORS/403.

**Verified on:** anikage (the original bug: relative `/api/proxy` URL passed to
ExoPlayer → host-less Uri → no subs). Fixed by explicit BASE absolutization + `en`
code. just4anime returns `en`/`id`/`th` VTTs; backend proxies them.

---

## M8. Title → slug normalization

**Symptom:** You have the anime **title** (from the app) but the source needs a URL
slug.

**Mechanism:**
- English: lowercase, strip non-alphanumerics, spaces→`-`. Try variants:
  `<slug>`, `<slug>-tv`, `<slug>-dub`, strip `:`/`.`.
- Romaji: many sources (animegg) use **romaji/Japanese** slugs that English titles
  can't produce. **Reuse the aggregator's `episode.id` slug** when valid — it's already
  in the source's format. Only fall back to title-based guessing when that's corrupt.
- Detect corrupt slugs: if the slug contains a different show's name (e.g. `your-name`
  for a Black Clover request), reject it and use the title.

**Verified on:** ryuk/animegg — just4anime's `episode.id` was `your-name$ep-1` for
Black Clover (corrupt); title fallback `black-clover-tv-episode-N` worked.

---

## Decision tree (which method first?)

```
API gives a stream URL?
├─ it's a cors proxy token (M1) ──> fetch with referer; if 200+HLS, done.
│                                 └─ if 403/intermittent ──> try to decode upstream (M3/M4)
├─ API gives an iframe URL ──> fetch iframe (M2)
│   ├─ literal m3u8 in JS ──> return it + referer
│   └─ eval(p,a,c,k,e,d) packer ──> node-decode (M3)
├─ stream plays WRONG content ──> resolve from real source yourself (M4)
└─ it's a .mp4 ──> return + hardcode referer (M5)

Always: verify 200 + valid HLS + a segment downloads (M-referer check).
Always: absolutize subtitles + 2-letter lang (M7).
```
