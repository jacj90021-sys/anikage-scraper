# anikage-scraper

Resolves real, playable video URLs (m3u8 / mp4) for any episode on
[anikage.cc](https://anikage.cc), reverse-engineered from the live site
(verified against `https://anikage.cc/anime/watch/ARPEGZW3fK?ep=1`, Aug 2026).

## How it works

1. **Catalog / server list** (clean JSON API, needs only a `Referer`):
   - `GET /api/media/anime/<slug>/episodes`
   - `GET /api/media/anime/<slug>/episodes/<n>/servers`
2. **Stream resolution**:
   `GET /api/media/anime/<slug>/episodes/<n>/sources?provider=<id>&lang=sub|dub`

Every source `url` from step 2 is `base64( XOR with repeating key b"aproxy2026" )`.
Decrypting it yields the **real upstream URL directly** — no prox relay, no
embed-page scraping. The same decrypt resolves every provider:

| Server | Real stream |
|---|---|
| Neko (softsub) | `https://vivibebe.site/public/stream/<hash>/master.m3u8` (hls) |
| Ken / dib (hardsub) | `https://playeng.animeapps.top/r2/cachehd/.../index.m3u8` (hls) |
| Megg | `https://s<nnn>.vidcache.net:<port>/play/<token>/video.mp4` (mp4) |
| Wave | `https://<cdn>.echovideo.to/cdn/<token>?t.m3u8` (hls) |
| Koto / E-Koto / E-Wish | `https://megap.<cdn>/<token>/<hash>/master.m3u8` (hls) |

For Koto/E-Wish the scraper also calls the megaplay player endpoint
(`https://megaplay.buzz/stream/getSources?id=<data-id>`, with `Referer` +
`Origin` = `https://megaplay.buzz`) to attach the subtitle track and the
intro/outro skip timestamps. The `<data-id>` is parsed from the megaplay
embed page (the `s-<n>/<realid>` path number is **not** the getSources id).

## CLI

```bash
# search the catalog
python3 anikage_scraper.py --search "one piece"

# list servers + embeds for an episode
python3 anikage_scraper.py --stream --slug ARPEGZW3fK --ep 1          # default Neko
python3 anikage_scraper.py --stream --slug ARPEGZW3fK --ep 1 --provider E-Wish
python3 anikage_scraper.py --stream --slug ARPEGZW3fK --ep 1 --provider megg --lang dub
```

Output:

```json
{
  "slug": "ARPEGZW3fK",
  "episode": "1",
  "lang": "sub",
  "provider": "E-Wish",
  "quality": "HD-1 auto",
  "url": "https://megap.mikora.top/f899139df5e1059396431415e770c6dd/61b87186ab260d05003427e16ccf5657/master.m3u8",
  "format": "hls",
  "referer": "https://megap.mikora.top/",
  "embed_url": "https://megaplay.buzz/stream/s-2/2142/sub",
  "subtitle": "https://1oe.lostproject.club/anime/.../eng-2.vtt",
  "intro": {"start": 31, "end": 111},
  "outro": {"start": 1376, "end": 1447}
}
```

The `referer` must be sent when the player fetches the stream or the CDN
returns 403.

## Web API (Flask)

```bash
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:3000
```

- `GET /api/search?q=one`
- `GET /api/anime/<slug>/episodes`
- `GET /api/anime/<slug>/servers?ep=1`
- `GET /api/anime/<slug>/stream?ep=1&provider=E-Wish&lang=sub`
- `GET /api/health`

## Notes

- The XOR key rotates yearly (`aproxy2024` → `aproxy2025` → `aproxy2026`);
  if decryption stops producing `https://` URLs, brute-force the new key from
  the known `https://` plaintext prefix (the key length stays 11).
- Keep requests slow — anikage returns `429` when hammered; the CLI sleeps
  briefly between providers.
