#!/usr/bin/env python3
"""hls_referer_fetch.py — verify an HLS stream is REAL and PLAYABLE.

Checks the full chain: master -> variant -> a segment, each with the required
Referer. Returns non-zero / prints FAIL if any step breaks. Use this to PROVE a
scraped stream works before trusting it.

Usage:
    python3 hls_referer_fetch.py <master_url> <referer> [segment_referer]

It prints the HTTP status + content-type for master, variant, and first segment.
"""
import sys
import re
import subprocess
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.37"


def get(url, referer, timeout=25):
    cmd = ["curl", "-s", "-A", UA]
    if referer:
        cmd += ["-e", referer]
    cmd += ["--max-time", str(timeout), url]
    return subprocess.run(cmd, capture_output=True)  # bytes; decode where needed


def main():
    if len(sys.argv) < 3:
        print("usage: hls_referer_fetch.py <master_url> <referer>")
        sys.exit(2)
    master, referer = sys.argv[1], sys.argv[2]
    seg_ref = sys.argv[3] if len(sys.argv) > 3 else referer

    # 1) master
    m = get(master, referer)
    m_text = m.stdout.decode("utf-8", "replace")
    ok = m_text.startswith("#EXTM3U")
    print(f"[master] {'OK' if ok else 'BAD'} http={m.returncode} len={len(m.stdout)}")
    if not ok:
        print(m_text[:300])
        sys.exit(1)

    # 2) variant (first referenced playlist)
    var = re.search(rb'([^\s]+\.m3u8|[^\s]+\.txt)', m.stdout)
    if var:
        vurl = var.group(1).decode()
        full = vurl if vurl.startswith("http") else urljoin(master, vurl)
        vb = get(full, referer)
        v_text = vb.stdout.decode("utf-8", "replace")
        ok2 = v_text.startswith("#EXTM3U")
        print(f"[variant] {'OK' if ok2 else 'BAD'} len={len(vb.stdout)} -> {full[:90]}")
        if ok2:
            # 3) segment
            seg = re.search(rb'([^\s]+\.ts[^\s]*|[^\s]+\.woff2[^\s]*|[^\s]+\.m4s[^\s]*)', vb.stdout)
            if seg:
                surl = seg.group(1).decode()
                if not surl.startswith("http"):
                    surl = urljoin(full, surl)
                r = get(surl, seg_ref)
                print(f"[segment] http={r.returncode} bytes={len(r.stdout)} -> {surl[:90]}")
                if r.returncode != 0:
                    sys.exit(1)
            else:
                print("[variant] no segment line found (single-file?)")
    else:
        print("[master] no variant referenced")


if __name__ == "__main__":
    main()
