#!/usr/bin/env python3
"""In-place TAE event patch: turn an existing event of an animation into
HideWeapon (710) without changing any file size.

Why in-place: the earlier attempts at *growing* the TAE (adding event headers /
event-group entries) were rejected by the game.  Rewriting the u64 event type and
its 4 parameter bytes inside an existing data block touches nothing else, so the
DCX/BND4/TAE containers stay byte-for-byte identical in layout and only the
compression stream is redone (which the game already accepted).

usage:
  py tae_inplace.py <in.dcx> <out.dcx> <animId>[,<animId>...] [--param 01000000]
                    [--pick last|700] [--dry]
"""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3bnd as B  # noqa: E402


def i64(d, o):
    return struct.unpack_from("<q", d, o)[0]


def i32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def u64(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def patch_tae(tae, targets, param, pick, allanims=False):
    """Return (new_bytes, report).  Sizes never change."""
    d = bytearray(tae)
    bank = i64(d, 0x20)
    cnt = i32(d, bank + 4)
    anims = i64(d, bank + 8)
    report = []
    for i in range(cnt):
        rec = anims + i * 16
        aid = i64(d, rec)
        if not allanims and aid not in targets:
            continue
        hdr = i64(d, rec + 8)
        if hdr == 0:
            continue
        evoff = i64(d, hdr)
        evcnt = i32(d, hdr + 0x20)
        if evcnt <= 0:
            continue
        # collect candidate events
        cands = []
        for k in range(evcnt):
            eh = evoff + k * 24
            do = i64(d, eh + 0x10)
            if do <= 0:
                continue
            cands.append((k, do, u64(d, do)))
        if not cands:
            continue
        # pick one to sacrifice
        chosen = None
        if pick == "700":
            for k, do, ty in cands:
                if ty == 700:
                    chosen = (k, do, ty)
                    break
        elif pick == "strict700":
            # only touch animations that contain a harmless Event[700]; skip the rest
            for k, do, ty in cands:
                if ty == 700:
                    chosen = (k, do, ty)
                    break
            if chosen is None:
                continue
        if chosen is None:
            chosen = cands[-1]          # default: the last event
        k, do, oldty = chosen
        if oldty == 710:
            report.append((aid, k, oldty, "already 710"))
            continue
        struct.pack_into("<Q", d, do, 710)
        d[do + 0x10:do + 0x14] = param
        report.append((aid, k, oldty, param.hex(" ")))
    return bytes(d), report


def main():
    inp, outp = sys.argv[1], sys.argv[2]
    allanims = sys.argv[3].upper() in ("ALL", "*")
    ids = set() if allanims else set(int(x, 0) for x in sys.argv[3].split(","))
    param = bytes.fromhex(sys.argv[sys.argv.index("--param") + 1]) if "--param" in sys.argv else bytes([1, 0, 0, 0])
    pick = sys.argv[sys.argv.index("--pick") + 1] if "--pick" in sys.argv else "last"
    dry = "--dry" in sys.argv

    data = B.load(inp)
    ents = B.entries(data)
    out = bytearray(data)
    total = 0
    for idx, (name, off, size, flags, fid) in enumerate(ents):
        base = os.path.basename(name)
        if not base.lower().endswith(".tae") or size == 0:
            continue
        tae = data[off:off + size]
        if tae[:4] != b"TAE ":
            continue
        new_tae, rep = patch_tae(tae, ids, param, pick, allanims)
        if rep:
            out[off:off + size] = new_tae          # same length: pure in-place ✓
            for aid, k, oldty, what in rep:
                print("  %-10s anim %-6d event %d/%s: type %d -> 710   param=%s" %
                      (base, aid, k + 1, "?", oldty, what))
                total += 1
    print("patched %d event(s); size %d -> %d (must be equal)" % (total, len(data), len(out)))
    if len(data) != len(out):
        print("ABORT: size changed, that is exactly what the game rejected before")
        return 1
    if dry:
        print("(dry run, nothing written)")
        return 0

    orig_dcx = open(inp, "rb").read()
    comp = zlib.compress(bytes(out), 9)
    head = bytearray(orig_dcx[:0x4C])
    struct.pack_into(">I", head, 0x1C, len(out))
    struct.pack_into(">I", head, 0x20, len(comp))
    with open(outp, "wb") as fh:
        fh.write(bytes(head) + comp)
    print("wrote %s (%d bytes)" % (outp, len(head) + len(comp)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
