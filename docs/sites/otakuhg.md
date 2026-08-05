# Site: otakuhg.site

The obfuscated-player backend used by just4anime's `sai`/`mai` servers. Serves the
real stream via a **packed jwplayer** script.

## Page structure
`https://otakuhg.site/e/<id>` → HTML with:
- `<title>` like `82145 sub 1920 1080 <ts></title>` (internal video id + type)
- A script block: `eval(function(p,a,c,k,e,d){while(c--)if(k[c])p=p.replace(...)}('packed',a,c,'k'.split('|')))`

The packer, when run, sets up jwplayer with `sources[0].file` = the real m3u8.

## Decode (M3)
1. Fetch the `/e/<id>` page (referer `https://otakuhg.site/`).
2. Extract the balanced-paren `eval(...)` block.
3. Run in node with a `jwplayer.setup` hook (see `templates/node_packer_decode.js`).
4. `SETUP_FILE:` stdout = e.g.
   `https://<random>.dietandnutritionist.site/<path>/<id>_o/master.txt`
   (extension `.txt`, but it's HLS. Segments use `.woff2` extension but are MPEG-TS.)

## Referer
`https://otakuhg.site/` — mandatory on master, variant, AND segments. Without it:
- master → 404
- segment → 404
With it: master 200 HLS, variant 200 (50KB), segment 200 `video/MP2T` ~292KB.

## Random CDN hosts observed
`*.dietandnutritionist.site`, `*.technologyintegration.space` — different per stream.
They are stable for a given `<id>`; resolve fresh each time (don't hardcode).

## Why not reverse the packer by hand?
The token scheme is base-`a` (a=36) with nested replaces; a Python regex gives
garbage. Running the real decoder in node is 10 lines and always correct.

## Verified
sai/sub + mai/dub decoded live; full playback chain confirmed (master→variant→segment).
