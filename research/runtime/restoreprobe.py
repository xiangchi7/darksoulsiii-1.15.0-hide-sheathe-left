#!/usr/bin/env python3
"""Measure how fast the engine restores WepAbsorpPosParam after we overwrite it.

usage: py restoreprobe.py [rowId] [samples]
"""

import struct
import sys
import time

sys.path.insert(0, r"C:\Users\35866\Documents\deepseek-harness\default-workspace\ds3-hide-sheathed\tools")
import ds3probe as P  # noqa: E402

TABLES = [0x7FF427AD0500, 0x7FF427ADAAD0, 0x7FF4A0B1D160, 0x7FF4FD6CC0C0]
FIELDS = [0x0A, 0x14, 0x1E, 0x28]
HIDE = b"\xff\xff"

row_id = int(sys.argv[1], 0) if len(sys.argv) > 1 else 48
samples = int(sys.argv[2]) if len(sys.argv) > 2 else 6

g = P.Game()
targets = []
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
        if rid == row_id:
            targets.append((t, t + roff))
            break

print("restoreprobe: pid=%d row=%d tables=%d" % (g.pid, row_id, len(targets)), flush=True)
for n in range(samples):
    for _t, row in targets:
        for f in FIELDS:
            g.write(row + f, HIDE)
    t0 = time.perf_counter()
    restored = None
    while (time.perf_counter() - t0) < 3.0:
        first = g.read(targets[0][1] + FIELDS[0], 2)
        if first != HIDE:
            restored = (time.perf_counter() - t0) * 1000.0
            break
    if restored is None:
        print("  sample %d: NOT restored within 3 s (value %s)" %
              (n, g.read(targets[0][1] + FIELDS[0], 2).hex(" ")), flush=True)
    else:
        print("  sample %d: restored after %.3f ms" % (n, restored), flush=True)
    time.sleep(0.4)

g.close()
