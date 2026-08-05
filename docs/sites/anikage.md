# Site: anikage.cc (anikage-scraper)

The first backend we built. Python + Flask, mirrors the contract used by the
AniwaveStream app. Documents the **subtitle bug** that became a general rule (M7).

## Method
- Reverse-engineered anikage's embed flow (M2-style): iframe → literal m3u8.
- Flask API: `/api/anime/<id>/servers`, `/api/anime/<id>/stream`,
  `/api/proxy` (subtitles).
- Bind `$PORT` for Render.

## The subtitle bug (M7)
Original app passed a **relative** `/api/proxy?url=...` subtitle URL to ExoPlayer.
ExoPlayer built a host-less `Uri` → **silent failure** (subs never showed, no crash).
Fix: **absolutize the subtitle URL against the backend BASE** before sending to
ExoPlayer, AND use **2-letter** lang codes (`en` not `eng`) so `TrackSelector` matches.
This is the #1 silent failure mode — check it first if "video plays but no subs".

## Repo
`github.com/jacj90021-sys/anikage-scraper`

## Lesson
When reusing this contract for a new site, copy the absolutization + 2-letter mapping
exactly. Don't "simplify" it.
