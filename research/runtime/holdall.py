#!/usr/bin/env python3
"""Keep leftHang_0..3 = -1 in every row of every WepAbsorpPosParam copy (the exact
1.0.0 core effect), re-asserting continuously.

usage: py holdall.py [seconds] [intervalSeconds]
"""

import struct
import sys
import time

sys.path.insert(0, r"C:\Users\35866\Documents\deepseek-harness\default-workspace\ds3-hide-sheathed\tools")
import ds3probe as P  # noqa: E402

TABLES = [0x7FF427AD0500, 0x7FF427ADAAD0, 0x7FF4A0B1D160, 0x7FF4FD6CC0C0]
FIELDS = [0x0A, 0x14, 0x1E, 0x28]          # leftHang_0..3 only
HIDE = b"\xff\xff"

duration = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0
interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.001

g = P.Game()
rows = []
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
        rows.append((rid, t + roff))

print("holdall: pid=%d rows=%d fields=%s interval=%.4fs" %
      (g.pid, len(rows), [hex(f) for f in FIELDS], interval), flush=True)

end = time.time() + duration
next_report = time.time() + 1.0
passes = 0
writes = 0
try:
    while time.time() < end:
        for _rid, row in rows:
            for f in FIELDS:
                if g.read(row + f, 2) != HIDE:
                    if g.write(row + f, HIDE):
                        writes += 1
        passes += 1
        if time.time() >= next_report:
            print("holdall: %d passes, %d writes, %.1f passes/s" %
                  (passes, writes, passes / max(1e-6, duration - (end - time.time()))),
                  flush=True)
            next_report = time.time() + 1.0
        if interval > 0:
            time.sleep(interval)
finally:
    g.close()
    print("holdall: done, %d passes, %d writes" % (passes, writes), flush=True)
