"""Crop a ds3shot PNG and save it (for tight visual inspection).

  python pngcrop.py in.png out.png x0,y0,x1,y1 [--scale 1]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3shot as S       # noqa: E402
import pngdiff as D       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("rect")
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args()

    w, h, img = D.read_png(args.src)
    ox, oy, x1, y1 = (int(v) for v in args.rect.split(","))
    x1, y1 = min(x1, w), min(y1, h)
    cw, ch = x1 - ox, y1 - oy
    rows = [img[(y * w + ox) * 4:(y * w + x1) * 4] for y in range(oy, y1)]
    data = b"".join(rows)
    if args.scale > 1:
        s = args.scale
        out = []
        for y in range(0, ch, s):
            row = data[y * cw * 4:(y + 1) * cw * 4]
            out.append(b"".join(row[x * 4:x * 4 + 4] for x in range(0, cw, s)))
        data, cw, ch = b"".join(out), len(range(0, cw, s)), len(range(0, ch, s))
    S.write_png(args.dst, cw, ch, data)
    print(f"wrote {args.dst} ({cw}x{ch})")


if __name__ == "__main__":
    main()
