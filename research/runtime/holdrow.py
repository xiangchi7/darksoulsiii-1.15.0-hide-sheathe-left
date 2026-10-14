#!/usr/bin/env python3
"""Re-apply the hide patch to a single WepAbsorpPosParam row as fast as possible.

The engine selects the row through the weapon's WepAbsorpPosID, so patching the
one row the player's left-hand item uses is enough -- and only 4 * 4 = 16 writes
per pass, which fits inside a single frame.

usage: py holdrow.py [rowId] [seconds] [--allfields]
"""

import struct
import sys
import time

sys.path.insert(0, r"C:\Users\35866\Documents\deepseek-harness\default-workspace\ds3-hide-sheathed\tools")
import ds3probe as P  # noqa: E402

TABLES = [0x7FF427AD0500, 0x7FF427ADAAD0, 0x7FF4A0B1D160, 0x7FF4FD6CC0C0]
FIELDS = [0x0A, 0x14, 0x1E, 0x28]          # leftHang_0..3  (the 1.0.0 core)
if "--allfields" in sys.argv:
    FIELDS += [0x0E, 0x18, 0x22]           # right_1..3 (paired offhand)
HIDE = b"\xff\xff"

row_id = int(sys.argv[1], 0) if len(sys.argv) > 1 else 48
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0

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

print("holdrow: pid=%d row=%d tables=%d fields=%s" %
      (g.pid, row_id, len(targets), [hex(f) for f in FIELDS]), flush=True)
before = [g.read(row + FIELDS[0], 2).hex(" ") for _, row in targets]
print("holdrow: before 0x0A = %s" % before, flush=True)

end = time.time() + duration
passes = 0
try:
    while time.time() < end:
        for _t, row in targets:
            for f in FIELDS:
                g.write(row + f, HIDE)
        passes += 1
finally:
    after = [g.read(row + FIELDS[0], 2).hex(" ") for _, row in targets]
    print("holdrow: %d passes, after 0x0A = %s" % (passes, after), flush=True)
    g.close()
