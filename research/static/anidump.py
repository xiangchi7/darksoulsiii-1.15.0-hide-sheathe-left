#!/usr/bin/env python3
"""Dump a range of a decompressed DS3 bundle and look for embedded magics.

usage: py anidump.py <bundle> <start> <len>
"""

import os
import struct
import sys
import zlib


def read_dcx(path):
    data = open(path, "rb").read()
    if data[:4] != b"DCX\x00":
        return data
    for magic in (b"\x78\xda", b"\x78\x9c", b"\x78\x01", b"\x78\x5e"):
        i = data.find(magic, 0x24)
        if i >= 0:
            d = zlib.decompressobj()
            out = d.decompress(data[i:])
            try:
                out += d.flush()
            except Exception:
                pass
            return out
    raise SystemExit("no zlib stream")


def main():
    path = sys.argv[1]
    start = int(sys.argv[2], 0)
    n = int(sys.argv[3], 0)
    data = read_dcx(path)
    print("%s -> %d bytes" % (os.path.basename(path), len(data)))

    print("\n-- dump 0x%X..0x%X --" % (start, start + n))
    for k in range(start, start + n, 16):
        chunk = data[k:k + 16]
        print("  %06X  %-47s  %s" % (k, chunk.hex(" "),
                                     "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)))

    print("\n-- embedded magic scan --")
    for magic in (b"TAE\x00", b"TAE ", b"TAE0", b"TAE\0\0", b"TAE\x01", b"TAE\x02",
                  b"HKX", b"TAG0", b"BND4", b"FXR3", b"FSB5"):
        cnt = 0
        pos = 0
        first = None
        while True:
            i = data.find(magic, pos)
            if i < 0:
                break
            cnt += 1
            if first is None:
                first = i
            pos = i + 1
        if cnt:
            print("  %-8r %6d hit(s), first at 0x%X" % (magic, cnt, first))

    # records: name-offset value 0x26EE was found at 0x84; assume stride 0x24
    print("\n-- record table probe (stride 0x24) --")
    for idx in range(3):
        rec = 0x70 + idx * 0x24
        vals = struct.unpack_from("<IIIIIIII", data, rec)
        print("  rec[%d]@0x%X: %s" % (idx, rec, " ".join("%08X" % v for v in vals)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
