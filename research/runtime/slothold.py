#!/usr/bin/env python3
"""Hold the left-hand equipment slot at "empty" (110000) and measure how often the
engine rewrites it.

usage: py slothold.py [seconds]
"""

import struct
import sys
import time

sys.path.insert(0, r"C:\Users\35866\Documents\deepseek-harness\default-workspace\ds3-hide-sheathed\tools")
import ds3probe as P  # noqa: E402

SLOTS = [0x7FF4AB9B3390, 0x7FF4AB9B3394,
         0x7FF4AD39C038, 0x7FF4AD3A66A0]
EMPTY = struct.pack("<I", 110000)

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0

g = P.Game()
print("slothold: pid=%d slots=%s empty=110000" % (g.pid, [hex(a) for a in SLOTS]), flush=True)
print("slothold: before = %s" % [g.u32(a) for a in SLOTS], flush=True)

end = time.time() + seconds
passes = 0
flips = 0
restored_samples = 0
try:
    while time.time() < end:
        for a in SLOTS:
            cur = g.read(a, 4)
            if cur != EMPTY:
                g.write(a, EMPTY)
                flips += 1
        passes += 1
        if passes % 500 == 0:
            vals = [g.u32(a) for a in SLOTS]
            bad = sum(1 for v in vals if v != 110000)
            print("slothold: %d passes, %d rewrites, last sample %s (non-empty=%d)" %
                  (passes, flips, vals, bad), flush=True)
finally:
    print("slothold: done, %d passes, %d rewrites (engine rewrote it)" % (passes, flips),
          flush=True)
    g.close()
