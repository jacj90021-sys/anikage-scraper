# Site: vivibebe.site / bibiemb.xyz / vibevibe.workers.dev

The embed hosts behind just4anime's `kai` and `zeke` servers (and others). These serve
real m3u8s **literally** in the page — no packer, no Cloudflare on the m3u8 itself.

## kai / zeke
- API gives `iframe: https://vivibebe.site/public/stream/<id>`
- The iframe page JS contains the literal m3u8:
  `https://vivibebe.site/public/stream/<id>/master.m3u8`
- Referer = `https://vivibebe.site/`
- zeke sub/hsub come from `vibevibe.workers.dev` (bibiemb.xyz iframe).
- dub (kai/zeke/sai/mai) routes to the same vivibebe stream id as sub — dub audio is
  an in-player track; the URL is identical.

## Extraction (M2)
Regex the page for `https://<host>/.../master.m3u8`. Return + host referer.

## Verified
JJK / Trapped S2 / Black Clover: all variants 200 HLS + subtitles 200 text/vtt.
These are the most reliable servers — prefer them.

## Note
If a host starts Cloudflare-limiting, the m3u8 still resolves but segments may 403
from a datacenter IP (user device is fine). Not observed to break yet.
