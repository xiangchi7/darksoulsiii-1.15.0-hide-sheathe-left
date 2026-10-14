#!/usr/bin/env python3
"""Save every memory location that holds the player's left-hand item id.

usage: py idscan.py <outfile> [value]
"""

import os
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import ds3probe as P  # noqa: E402

WINDOWS = [(0x7FF410000000, 0x10000000),
           (0x7FF490000000, 0x10000000),
           (0x7FF4A0000000, 0x10000000),
           (0x7FF4B0000000, 0x10000000)]
CHUNK = 1 << 22

outfile = sys.argv[1] if len(sys.argv) > 1 else "ids.txt"
value = int(sys.argv[2], 0) if len(sys.argv) > 2 else 21200000
pat = struct.pack("<I", value)

g = P.Game()
hits = []
for base, size in WINDOWS:
    off = 0
    while off < size:
        n = min(CHUNK, size - off)
        data = g.read(base + off, n)
        if data:
            pos = 0
            while True:
                i = data.find(pat, pos)
                if i < 0:
                    break
                hits.append(base + off + i)
                pos = i + 1
        off += n
g.close()

hits.sort()
with open(outfile, "w") as fh:
    for h in hits:
        fh.write("0x%X\n" % h)
print("idscan: value=%d  %d hit(s) saved to %s" % (value, len(hits), outfile))
for h in hits:
    print("  0x%X" % h)
