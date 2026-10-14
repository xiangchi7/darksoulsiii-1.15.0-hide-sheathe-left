#!/usr/bin/env python3
"""Re-apply the released 1.0.0 patch (leftHang_* / right_1..3 = -1) at a fixed
interval, to test whether the flicker is the gap between the engine refreshing
the parameter table and the mod re-applying its writes.

usage: py holdrelease.py [intervalSeconds] [durationSeconds]
"""

import struct
import sys
import time

sys.path.insert(0, r"C:\Users\35866\Documents\deepseek-harness\default-workspace\ds3-hide-sheathed\tools")
import ds3probe as P  # noqa: E402

TABLES = [0x7FF427AD0500, 0x7FF427ADAAD0, 0x7FF4A0B1D160, 0x7FF4FD6CC0C0]
FIELDS = [0x0A, 0x14, 0x1E, 0x28, 0x0E, 0x18, 0x22]
HIDE = b"\xff\xff"

interval = float(sys.argv[1]) if len(sys.argv) > 1 else 0.1
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0

g = P.Game()
print("holdrelease: pid=%d interval=%.3fs duration=%.0fs" % (g.pid, interval, duration),
      flush=True)

# cache the row table once
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
        rows.append(t + roff)
print("holdrelease: %d rows cached" % len(rows), flush=True)

end = time.time() + duration
passes = 0
try:
    while time.time() < end:
        for row in rows:
            for f in FIELDS:
                g.write(row + f, HIDE)
        passes += 1
        time.sleep(interval)
finally:
    g.close()
    print("holdrelease: done, %d passes" % passes, flush=True)
