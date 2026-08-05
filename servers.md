# Anikage Server Stream Links — Hunter x Hunter (2011) Episode 1

Scraped and verified live on 2026-08-05. Every URL below was fetched and confirmed to
return playable HLS (or MP4) content.

The site returns obfuscated blobs from its `sources` API. These are decoded by wrapping
them with anikage's own proxy: `https://prox.anikage.cc/<type>/<blob>` (type = `m3u8` or
`stream`). Requests need `Referer: https://anikage.cc/`. The raw CDN URLs (vivibebe,
vibevibe workers, megaplay) are also listed where still live.

## Neko (default)

| Quality | Type | URL |
|---|---|---|
| softsub HD-1 | HLS | `https://prox.anikage.cc/m3u8/CQQGHwtDHR9EXxcZEAoaHBxDW0IEXwIaGhVbUx1FFQIXDhVWVAgGDllJS19ASgQJBAZTFV0CGQpGVUAYDEMHV3gRRkRCRVtfXRkRD1tSV1QEXgEGDBwd` |
| softsub HD-2 | HLS | `https://prox.anikage.cc/m3u8/CQQGHwtDHR9fWRMeGwEfVFFCV1IIBF9cGhpRHkRfAxUEBhocHEddRAoVABxWHVdGHVcGQ0ZXHklWVQIOWEdCWk8YU1MAUgRHF1oaHVNUAQVWERZbEFZfUUFCBAJcAksMCjBaQhUAAVVXVlBZUF8EHRBBAABIHw` |

Direct CDN mirrors (also live as of check date):
- `https://vivibebe.site/public/stream/f84889908369602e/master.m3u8` (360/720/1080p)
- `https://morning-credit-3bcc.vibevibe.workers.dev/ag348f0de0897057aac2de7e5bdad337ad4h/master.m3u8` (360/720/1080p)

## Megg

| Quality | Type | URL |
|---|---|---|
| 360p | MP4 | `https://prox.anikage.cc/stream/CQQGHwtDHR9BB1lJXBkRHVFRUV4EXhwKDEMKAQQATgAeDgFWUwICBFdASl9MKXpmBQVZEkBaMk8dRltSBB9cAghNDRZRXwVNQ1hNQAUIAjYJBAYfC0MdH0VBFl4TAREUV1dVGA4CFUA` |

## Dib (hardsub, BD)

| Quality | Type | URL |
|---|---|---|
| SR auto | HLS | `https://prox.anikage.cc/m3u8/CQQGHwtDHR9CWgAJFwEfV1NeW1sEEQIfC1dGX0IZE0JdDBkaWlVaUk5BQ19OSFdSVgdOGRwLHQEcXQFDWXAaGwwJQQodGREcExYdF1UeU1gIHRcOCAlBHkZZEV8` |

## Wave

| Quality | Type | URL |
|---|---|---|
| Vidplay auto | HLS | `https://prox.anikage.cc/m3u8/CQQGHwtDHR9AQ0wTFgFJV1dTWlkXGRYKF1dGXx1VBR5dX0FLVwNWBAVBRlhLT1MAU1JUQ0pZT0ACCQZVAkIWWxobAgQGAlVIF15JG1FTAwUHFEVXQEgAAQoFUEhFDB5AV1YFBARHRFwdHFABC1RVEkIMQUEABFcEVRZKDhlJAQdWDlhJEw0eQFMJAA4CQkJcHB9RCQABB0dEWUEfAQEACRVeH1wNQTJYRkIRA0hAVwleUUsYBBMaAA4QVlVdGBMFXQ` |

## Koto

| Quality | Type | URL |
|---|---|---|
| HD-1 auto | HLS | `https://prox.anikage.cc/m3u8/CQQGHwtDHR9fUwYRAkEZEltCU05PEgcVAlZRCANTVkJKC0EdBlMAUFdDRAlITwVWCg8CE0NbQE8AUx0BUBUTWBxMUQVXVwUTFg4eGwZWAwIDSEZcHR1XBwEOB18fDgsNV0IcW1IFSm8QDUZAQQxOXx8KHxhCXFNPTxIHFQJW` |
| VidPlay-1 auto | HLS | `https://prox.anikage.cc/m3u8/CQQGHwtDHR9EXwUEBw1WFFtbXUQAXgYACFYKBAAFU0ZDC05PAgEEV1BAS11BH1RSVwcAE0VXTxwLAB1bAAMGCgpXXwNHDmEYBhsICggfHUAIFAYaGhwcQ1tCBF8` |

## Method

1. `GET /api/media/anime/<slug>/episodes/<n>/servers` -> server IDs (neko, megg, dib, wave, koto)
2. `GET /api/media/anime/<slug>/episodes/<n>/sources?provider=<id>&lang=sub` -> obfuscated `url` blobs
3. Real URL = `https://prox.anikage.cc/m3u8/<blob>` (m3u8) or `https://prox.anikage.cc/stream/<blob>` (mp4)
4. Needs `Referer: https://anikage.cc/`; the site now Cloudflare-challenges plain requests
   (a real browser or cloudscraper is required to reach the API).
