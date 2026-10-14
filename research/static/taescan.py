#!/usr/bin/env python3
"""Scan every TAE inside a DS3 animation bundle for TAE event ids.

usage: py taescan.py <cXXXX.anibnd.dcx> [--dump N]
"""

import os
import struct
import sys
import zlib

TARGETS = {710: "HideEquippedWeapon", 711: "HideModelMask", 212: "?", 100: "?"}


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
    data = read_dcx(path)
    print("%s -> %d bytes" % (os.path.basename(path), len(data)))

    offs = []
    pos = 0
    while True:
        i = data.find(b"TAE ", pos)
        if i < 0:
            break
        offs.append(i)
        pos = i + 4
    print("found %d TAE magic(s)" % len(offs))
    if not offs:
        return 1
    if "--dump" in sys.argv:
        n = int(sys.argv[sys.argv.index("--dump") + 1], 0)
        o = offs[0]
        print("first TAE at 0x%X:" % o)
        for k in range(0, n, 16):
            chunk = data[o + k:o + k + 16]
            print("  %+06X  %-47s  %s" % (k, chunk.hex(" "),
                                          "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)))

    # count occurrences of each event id as a little-endian u32 in every TAE region
    hits = {k: 0 for k in TARGETS}
    files_with = {k: 0 for k in TARGETS}
    for idx, o in enumerate(offs):
        end = offs[idx + 1] if idx + 1 < len(offs) else min(len(data), o + 0x40000)
        blob = data[o:end]
        for k in TARGETS:
            c = 0
            p = 0
            needle = struct.pack("<I", k)
            while True:
                j = blob.find(needle, p)
                if j < 0:
                    break
                c += 1
                p = j + 1
            hits[k] += c
            if c:
                files_with[k] += 1
    print("\nevent id occurrences across %d TAE block(s):" % len(offs))
    for k, name in TARGETS.items():
        print("  %-4d %-20s total=%d  in %d TAE block(s)" % (k, name, hits[k], files_with[k]))

    # list the first blocks that contain event 710, with the hit offsets
    print("\nTAE blocks containing event 710 (first 12):")
    shown = 0
    for idx, o in enumerate(offs):
        end = offs[idx + 1] if idx + 1 < len(offs) else min(len(data), o + 0x40000)
        blob = data[o:end]
        pos = blob.find(struct.pack("<I", 710))
        if pos < 0:
            continue
        name = "?"
        # name of this TAE: find the BND4 record whose dataOffset == o
        needle = struct.pack("<I", o)
        p = 0x40
        while p < min(len(data), 0x2680):
            if data[p:p + 4] == needle:
                rec = p - 0x18
                noff = struct.unpack_from("<I", data, rec + 0x20)[0]
                e = data.find(b"\x00\x00", noff)
                try:
                    name = data[noff:e + 1].decode("utf-16-le", "ignore").rstrip("\x00")
                except Exception:
                    pass
                break
            p += 1
        print("  [%3d] TAE@0x%-8X first710@+0x%-6X %s" % (idx, o, pos, name))
        shown += 1
        if shown >= 12:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
