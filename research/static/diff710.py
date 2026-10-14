#!/usr/bin/env python3
"""Diff the HideEquippedWeapon (710) events between two DS3 anibnd bundles.

usage: py diff710.py <original.dcx> <edited.dcx> [--event 710]
"""

import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3bnd as B  # noqa: E402


def i32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def i64(d, o):
    return struct.unpack_from("<q", d, o)[0]


def u64(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def parse_tae(d, base, event_id):
    """Return {animId: [(start, end, params_bytes), ...]} for one TAE at `base`."""
    bank = i64(d, base + 0x20)
    if bank <= 0 or base + bank + 0x10 > len(d):
        return None
    b = base + bank
    anim_count = i32(d, b + 4)
    anims_off = i64(d, b + 8)
    if anim_count <= 0 or anim_count > 100000:
        return None
    out = {}
    for i in range(anim_count):
        rec = base + anims_off + i * 16
        if rec + 16 > len(d):
            return None
        anim_id = i64(d, rec)
        off = i64(d, rec + 8)
        if off == 0:
            continue
        h = base + off
        if h + 0x24 > len(d):
            continue
        ev_off = i64(d, h)
        ev_count = i32(d, h + 0x20)
        if ev_count <= 0 or ev_count > 100000 or ev_off <= 0:
            continue
        evs = []
        for k in range(ev_count):
            eh = base + ev_off + k * 24
            if eh + 24 > len(d):
                break
            data_off = i64(d, eh + 0x10)
            if data_off == 0:
                continue
            dd = base + data_off
            if dd + 0x14 > len(d):
                continue
            if u64(d, dd) != event_id:
                continue
            start = struct.unpack_from("<f", d, base + i64(d, eh))[0]
            end = struct.unpack_from("<f", d, base + i64(d, eh + 8))[0]
            evs.append((round(start, 3), round(end, 3), bytes(d[dd + 0x10:dd + 0x14])))
        if evs:
            out[anim_id] = evs
    return out


def collect(path, event_id):
    data = B.load(path)
    ents = B.entries(data)
    res = {}
    for name, off, size, flags, fid in ents:
        if not name.lower().endswith(".tae"):
            continue
        short = os.path.basename(name.replace("\\", "/"))
        try:
            parsed = parse_tae(data, off, event_id)
        except Exception as exc:  # noqa: BLE001
            print("  !! %s parse error: %s" % (short, exc))
            continue
        if parsed is None:
            continue
        res[short] = parsed
    return res


def main():
    orig_path, edit_path = sys.argv[1], sys.argv[2]
    event_id = 710
    if "--event" in sys.argv:
        event_id = int(sys.argv[sys.argv.index("--event") + 1], 0)

    a = collect(orig_path, event_id)
    b = collect(edit_path, event_id)

    ta = sum(len(v) for m in a.values() for v in m.values())
    tb = sum(len(v) for m in b.values() for v in m.values())
    print("event %d: original %d event(s) in %d TAE file(s); edited %d event(s) in %d TAE file(s)"
          % (event_id, ta, len(a), tb, len(b)))

    hist_a = Counter(p for m in a.values() for evs in m.values() for (_, _, p) in evs)
    hist_b = Counter(p for m in b.values() for evs in m.values() for (_, _, p) in evs)
    print("\nparams histogram (original):")
    for k, v in hist_a.most_common():
        print("   %-14s %d" % (k.hex(" "), v))
    print("params histogram (edited):")
    for k, v in hist_b.most_common():
        print("   %-14s %d" % (k.hex(" "), v))

    print("\nper-TAE-file differences:")
    for short in sorted(set(a) | set(b)):
        ma, mb = a.get(short, {}), b.get(short, {})
        na = sum(len(v) for v in ma.values())
        nb = sum(len(v) for v in mb.values())
        if na == nb and ma == mb:
            continue
        print("  %-14s original %3d  edited %3d" % (short, na, nb))
        for aid in sorted(set(ma) | set(mb)):
            ea = ma.get(aid, [])
            eb = mb.get(aid, [])
            if ea == eb:
                continue
            print("     anim %-7d orig=%s  edit=%s"
                  % (aid,
                     " ".join("%s@%s" % (p.hex(" "), s) for s, _, p in ea) or "-",
                     " ".join("%s@%s" % (p.hex(" "), s) for s, _, p in eb) or "-"))


if __name__ == "__main__":
    main()
