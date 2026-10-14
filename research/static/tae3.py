#!/usr/bin/env python3
"""TAE3 parser: dump the HideWeapon (710) events of a DS3 TAE with their parameters.

usage: py tae3.py <cXXXX.anibnd.dcx> <entryName> [--max N] [--id <animId>]
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3bnd as B  # noqa: E402


def u64(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def i64(d, o):
    return struct.unpack_from("<q", d, o)[0]


def i32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def find_block(d, base, hint, span=0x80):
    """Locate an event data block near `hint` by its self-pointer signature.

    Event.WriteData writes:  uint64 Type; int64 (Position + 8); params; pad(0x10)
    so at a real block start P the 8 bytes at P+8 equal (P - taeBase) + 8.
    """
    for p in range(hint - span, hint + span + 1, 8):
        if p < 0 or p + 16 > len(d):
            continue
        if u64(d, p + 8) == (p - base) + 8:
            return p
    return None


def parse(d, base, max_hits=60, only_id=None):
    bank = i64(d, base + 0x20)
    b = base + bank
    bank_id = i32(d, b)
    anim_count = i32(d, b + 4)
    anims_off = i64(d, b + 8)
    print("  TAE@0x%X bank@+0x%X bankId=%d animCount=%d animsOffset=0x%X" %
          (base, bank, bank_id, anim_count, anims_off))
    found = 0
    for i in range(anim_count):
        rec = base + anims_off + i * 16
        anim_id = i64(d, rec)
        off = i64(d, rec + 8)
        if off == 0:
            continue
        h = base + off
        if only_id is not None and anim_id != only_id:
            continue
        ev_off = i64(d, h)
        ev_count = i32(d, h + 0x20)
        if ev_count <= 0:
            continue
        for k in range(ev_count):
            eh = base + ev_off + k * 24
            data_off = i64(d, eh + 0x10)
            if data_off == 0:
                continue
            dd = base + data_off
            etype = u64(d, dd)
            if etype != 710 and "--any" not in sys.argv:
                continue
            params = d[dd + 0x10:dd + 0x14]
            print("    anim %-6d type=%-6d params=%s  (start=%.3f end=%.3f)"
                  "  dataOff=0x%X abs=0x%X" %
                  (anim_id, etype, params.hex(" "),
                   struct.unpack_from("<f", d, base + i64(d, eh))[0],
                   struct.unpack_from("<f", d, base + i64(d, eh + 8))[0],
                   data_off, dd))
            if "--raw" in sys.argv:
                lo = dd - 0x20
                for q in range(lo, dd + 0x30, 8):
                    val = u64(d, q)
                    print("        %+06d  0x%016X   %s" %
                          (q - dd, val, d[q:q + 8].hex(" ")))
            found += 1
            break
        if found >= max_hits:
            print("    ... (stopping at %d)" % max_hits)
            break
    print("  animations with a 710 event shown: %d" % found)
    return found


def main():
    path = sys.argv[1]
    name = sys.argv[2]
    max_hits = 60
    if "--max" in sys.argv:
        max_hits = int(sys.argv[sys.argv.index("--max") + 1], 0)
    only = None
    if "--id" in sys.argv:
        only = int(sys.argv[sys.argv.index("--id") + 1], 0)
    data = B.load(path)
    ents = B.entries(data)
    sel = [(n, o, s) for n, o, s, f, fid in ents if name.lower() in n.lower()]
    if not sel:
        print("no entry matches %r" % name)
        return 1
    n, off, size = sel[0]
    print("%s -> %s off=0x%X size=%d" % (os.path.basename(path), os.path.basename(n), off, size))
    parse(data, off, max_hits, only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
