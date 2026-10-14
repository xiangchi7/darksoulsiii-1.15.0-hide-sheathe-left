"""Compose crops of several ds3shot PNGs side by side into one image.

  python pngsbs.py out.png x0,y0,x1,y1 in1.png in2.png [...]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3shot as S       # noqa: E402
import pngdiff as D       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dst")
    ap.add_argument("rect")
    ap.add_argument("srcs", nargs="+")
    ap.add_argument("--gap", type=int, default=6)
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args()

    ox, oy, x1, y1 = (int(v) for v in args.rect.split(","))
    panels = []
    for src in args.srcs:
        w, h, img = D.read_png(src)
        x1c, y1c = min(x1, w), min(y1, h)
        cw, ch = x1c - ox, y1c - oy
        rows = [img[(y * w + ox) * 4:(y * w + x1c) * 4] for y in range(oy, y1c)]
        panels.append((cw, ch, b"".join(rows)))

    s = max(1, args.scale)
    total_w = sum(p[0] // s for p in panels) + args.gap * (len(panels) - 1)
    max_h = max(p[1] // s for p in panels)
    out = bytearray(total_w * max_h * 4)
    bar = bytes([0, 0, 0, 255]) * args.gap
    xoff = 0
    for cw, ch, data in panels:
        nw, nh = cw // s, ch // s
        for y in range(nh):
            src_row = data[(y * s) * cw * 4:(y * s + 1) * cw * 4]
            row = b"".join(src_row[x * s * 4:x * s * 4 + 4] for x in range(nw))
            o = (y * total_w + xoff) * 4
            out[o:o + len(row)] = row
        xoff += nw
        if xoff < total_w:
            for y in range(max_h):
                o = (y * total_w + xoff) * 4
                out[o:o + len(bar)] = bar
            xoff += args.gap
    S.write_png(args.dst, total_w, max_h, bytes(out))
    print(f"wrote {args.dst} ({total_w}x{max_h}) from {len(panels)} panels")


if __name__ == "__main__":
    main()
