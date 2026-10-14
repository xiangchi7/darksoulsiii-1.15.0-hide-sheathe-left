"""Compare two ds3shot PNGs and crop the changed region.

  python pngdiff.py a.png b.png [--prefix out/diff --threshold 12 --pad 60]

Prints the number of changed pixels, mean absolute difference and the bounding
box of the change, then writes <prefix>-a.png / <prefix>-b.png crops (only when
the change is big enough to matter).
"""

import argparse
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3shot as S  # noqa: E402


def read_png(path):
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a png")
    pos, idat, w, h = 8, bytearray(), None, None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, bd, ct, _c, _f, inter = struct.unpack(">IIBBBBB", chunk)
            if bd != 8 or ct != 6 or inter != 0:
                raise ValueError(f"unsupported png: depth={bd} color={ct} interlace={inter}")
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = w * 4
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 0:
            pass
        elif f == 1:
            for i in range(4, stride):
                line[i] = (line[i] + line[i - 4]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--threshold", type=int, default=18)
    ap.add_argument("--pad", type=int, default=70)
    ap.add_argument("--rect", default=None,
                    help="restrict everything to x0,y0,x1,y1 of the source images")
    args = ap.parse_args()

    w1, h1, A = read_png(args.a)
    w2, h2, B = read_png(args.b)
    if (w1, h1) != (w2, h2):
        print(f"size mismatch {w1}x{h1} vs {w2}x{h2}")
        return 1
    w, h = w1, h1
    ox = oy = 0
    if args.rect:
        ox, oy, rx1, ry1 = (int(v) for v in args.rect.split(","))
        rx1, ry1 = min(rx1, w), min(ry1, h)
        cw, ch = rx1 - ox, ry1 - oy
        A = b"".join(A[(y * w + ox) * 4:(y * w + rx1) * 4] for y in range(oy, ry1))
        B = b"".join(B[(y * w + ox) * 4:(y * w + rx1) * 4] for y in range(oy, ry1))
        w, h = cw, ch
    stride = w * 4
    count = 0
    total = 0
    minx, miny, maxx, maxy = w, h, -1, -1
    rows_changed = []
    for y in range(h):
        o = y * stride
        ra, rb = A[o:o + stride], B[o:o + stride]
        rowdiff = 0
        for x in range(w):
            i = x * 4
            d = abs(ra[i] - rb[i]) + abs(ra[i + 1] - rb[i + 1]) + abs(ra[i + 2] - rb[i + 2])
            total += d
            if d > args.threshold:
                count += 1
                rowdiff += 1
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
        if rowdiff:
            if y < miny:
                miny = y
            maxy = y
            rows_changed.append((y, rowdiff))
    npx = w * h
    print(f"size        : {w}x{h}")
    print(f"changed px  : {count} ({100.0 * count / npx:.3f}%)  threshold={args.threshold}")
    print(f"mean abs diff: {total / npx:.2f} (sum of |dR|+|dG|+|dB| per px)")
    if count:
        print(f"bbox        : x {minx}..{maxx}  y {miny}..{maxy}")
        worst = sorted(rows_changed, key=lambda t: -t[1])[:5]
        print(f"busiest rows: {worst}")
    else:
        print("bbox        : none")

    if args.prefix and count > 200:
        x0 = max(0, minx - args.pad)
        x1 = min(w, maxx + args.pad)
        y0 = max(0, miny - args.pad)
        y1 = min(h, maxy + args.pad)
        for name, img in ((f"{args.prefix}-a.png", A), (f"{args.prefix}-b.png", B)):
            cw, ch = x1 - x0, y1 - y0
            rows = [img[(y * w + x0) * 4:(y * w + x1) * 4] for y in range(y0, y1)]
            S.write_png(name, cw, ch, b"".join(rows))
            print(f"wrote {name} ({cw}x{ch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
