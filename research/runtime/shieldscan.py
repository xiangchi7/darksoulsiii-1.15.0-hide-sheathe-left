#!/usr/bin/env python3
"""Automated "is the sheathed left-hand item drawn?" search over the dummy-poly
values of the row the item uses (WepAbsorpPosParam row 48 for the Grass Crest
Shield).

For each candidate value it patches the row, takes a few screenshots and reports
how far each shot is from the untouched baseline.  A value that (a) differs a lot
from the baseline and (b) does so consistently is a stable "item not drawn".

usage:
  py shieldscan.py baseline [n]                 -> baseline shots (row untouched)
  py shieldscan.py test <value> [n]             -> patch value, shoot, compare
  py shieldscan.py sweep <lo> <hi> [n]          -> sweep a value range
  py shieldscan.py restore                      -> put the original values back
"""

import os
import struct
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import ds3probe as P          # noqa: E402
import pngdiff                # noqa: E402
import ds3shot                # noqa: E402

TABLE = 0x7FF427AD0500        # first copy; all four are patched
TABLES = [0x7FF427AD0500, 0x7FF427ADAAD0, 0x7FF4A0B1D160, 0x7FF4FD6CC0C0]
ROW_ID = 48
FIELDS = [0x0A, 0x14, 0x1E, 0x28, 0x30, 0x32, 0x34, 0x36]   # leftHang_0..3 + leftBoth_0..3
OUT = os.path.join(os.path.dirname(TOOLS), "shots")
CROP = "480,240,800,660"      # x0,y0,x1,y1 of the 1280x720 capture around the character


def rows_of(g):
    out = []
    for t in TABLES:
        head = g.read(t, 0x40)
        if not head:
            continue
        length = struct.unpack("<H", head[0x0A:0x0C])[0]
        for i in range(length):
            info = g.read(t + 0x40 + i * 0x18, 0x18)
            if not info:
                break
            rid, roff = struct.unpack("<QQ", info[:16])
            if rid == ROW_ID:
                out.append(t + roff)
                break
    return out


def shot(path):
    subprocess.check_call([sys.executable, os.path.join(TOOLS, "ds3shot.py"),
                           path, "--scale", "0.5"],
                          stdout=subprocess.DEVNULL)


def diff_stats(a, b):
    w1, h1, A = pngdiff.read_png(a)
    w2, h2, B = pngdiff.read_png(b)
    if (w1, h1) != (w2, h2):
        return None
    ox, oy, rx1, ry1 = (int(v) for v in CROP.split(","))
    rx1, ry1 = min(rx1, w1), min(ry1, h1)
    w, h = rx1 - ox, ry1 - oy
    stride = w1 * 4
    count = 0
    total = 0
    for y in range(oy, ry1):
        o = y * stride + ox * 4
        ra = A[o:o + w * 4]
        rb = B[o:o + w * 4]
        for x in range(w):
            i = x * 4
            d = abs(ra[i] - rb[i]) + abs(ra[i + 1] - rb[i + 1]) + abs(ra[i + 2] - rb[i + 2])
            total += d
            if d > 18:
                count += 1
    npx = w * h
    return count * 100.0 / npx, total / npx


def take(tag, n):
    os.makedirs(OUT, exist_ok=True)
    paths = []
    for i in range(n):
        p = os.path.join(OUT, "%s-%02d.png" % (tag, i))
        shot(p)
        paths.append(p)
        time.sleep(0.25)
    return paths


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    g = P.Game()
    try:
        rows = rows_of(g)
        print("rows=%d  (fields %s)" % (len(rows), [hex(f) for f in FIELDS]), flush=True)
        if cmd == "baseline":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            orig = {}
            for f in FIELDS:
                orig[f] = g.read(rows[0] + f, 2)
            print("original values:", {hex(f): v.hex(" ") for f, v in orig.items()}, flush=True)
            paths = take("base", n)
            print("baseline shots:", len(paths), flush=True)
            for p in paths[1:]:
                print("  noise vs first: %.3f%% / %.2f" % diff_stats(paths[0], p), flush=True)
        elif cmd == "test":
            value = int(sys.argv[2], 0)
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
            payload = struct.pack("<H", value & 0xFFFF)
            for row in rows:
                for f in FIELDS:
                    g.write(row + f, payload)
            paths = take("v%04X" % (value & 0xFFFF), n)
            base = os.path.join(OUT, "base-00.png")
            for p in paths:
                st = diff_stats(base, p)
                print("  %s  changed=%.3f%%  mad=%.2f" % (os.path.basename(p), st[0], st[1]),
                      flush=True)
        elif cmd == "sweep":
            lo, hi = int(sys.argv[2], 0), int(sys.argv[3], 0)
            n = int(sys.argv[4]) if len(sys.argv) > 4 else 3
            base = os.path.join(OUT, "base-00.png")
            for value in range(lo, hi + 1):
                payload = struct.pack("<H", value)
                for row in rows:
                    for f in FIELDS:
                        g.write(row + f, payload)
                time.sleep(0.15)
                stats = []
                for i in range(n):
                    p = os.path.join(OUT, "sweep.png")
                    shot(p)
                    stats.append(diff_stats(base, p))
                    time.sleep(0.1)
                cs = [s[0] for s in stats]
                print("  value=%-5d changed=%s" %
                      (value, " ".join("%.2f%%" % c for c in cs)), flush=True)
        elif cmd == "restore":
            V = {0x0A: 0x30, 0x14: 0x1F, 0x1E: 0x00, 0x28: 0x00,
                 0x30: 0x19, 0x32: 0x1F, 0x34: 0x00, 0x36: 0x00}
            for row in rows:
                for f, v in V.items():
                    g.write(row + f, struct.pack("<H", v))
            print("restored", flush=True)
    finally:
        g.close()


if __name__ == "__main__":
    main()
