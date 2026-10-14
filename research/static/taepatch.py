#!/usr/bin/env python3
"""Splice HideWeapon (710) events into selected animations of a DS3 TAE bundle.

Strategy (append-only, safest):
  * inside each TAE, copy the target animation's 24-byte event-header array to the very
    end of the TAE and append one extra header that reuses an existing 710 data block
    with the requested parameters.  Nothing already in the TAE moves, so all existing
    offsets stay valid; only the animation's eventHeadersOffset and eventCount change.
  * then rebuild the BND4 (entry sizes, later data offsets, later name offsets) and
    recompress the DCX wrapper.

usage:
  py taepatch.py <in.dcx> <out.dcx> <idfile> [--param 01000000] [--dry] [--max N]
"""

import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3bnd as B  # noqa: E402


def load_ids(path):
    ids = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(int(line.split("\t")[0].split()[0], 0))
    return ids


def tae_regions(data):
    """Yield (entryName, off, size) for every *.tae entry."""
    for name, off, size, flags, fid in B.entries(data):
        if name.lower().endswith(".tae"):
            yield os.path.basename(name), off, size


def patch_one_tae(tae, targets, param, max_n):
    """Return (new_tae_bytes, list_of_(animId, newEventCount))."""
    d = bytearray(tae)
    bank = struct.unpack_from("<q", d, 0x20)[0]
    cnt = struct.unpack_from("<i", d, bank + 4)[0]
    anims = struct.unpack_from("<q", d, bank + 8)[0]

    def i64(o):
        return struct.unpack_from("<q", d, o)[0]

    def i32(o):
        return struct.unpack_from("<i", d, o)[0]

    # locate a donor: an event header whose data block is type 710 with the wanted params
    donor = None
    for i in range(cnt):
        rec = anims + i * 16
        aoff = i64(rec + 8)
        if aoff == 0:
            continue
        evoff = i64(aoff)
        evcnt = i32(aoff + 0x20)
        for k in range(evcnt):
            eh = evoff + k * 24
            do = i64(eh + 0x10)
            if do <= 0:
                continue
            if struct.unpack_from("<Q", d, do)[0] == 710 and bytes(d[do + 0x10:do + 0x14]) == param:
                donor = bytes(d[eh:eh + 24])
                break
        if donor:
            break

    changed = []
    if donor is None:
        return bytes(d), changed

    for i in range(cnt):
        if len(changed) >= max_n:
            break
        rec = anims + i * 16
        aid = i64(rec)
        aoff = i64(rec + 8)
        if aoff == 0 or aid not in targets:
            continue
        hdr = aoff
        evoff = i64(hdr)
        evcnt = i32(hdr + 0x20)
        if evoff <= 0 or evcnt < 0:
            continue
        # already has a 710 with these params?
        have = False
        for k in range(evcnt):
            do = i64(evoff + k * 24 + 0x10)
            if do > 0 and struct.unpack_from("<Q", d, do)[0] == 710 \
                    and bytes(d[do + 0x10:do + 0x14]) == param:
                have = True
                break
        if have:
            continue
        # copy the header array to the end of the TAE, then append
        #   * two fresh time floats (0.0 .. 999.0)   <- must belong to this animation
        #   * the new event header pointing at them and at a copied data block
        new_off = len(d)
        d += bytes(d[evoff:evoff + evcnt * 24])
        t_off = len(d)
        d += struct.pack("<ff", 0.0, 999.0)
        hdr24 = bytearray(donor)
        struct.pack_into("<q", hdr24, 0x00, t_off)
        struct.pack_into("<q", hdr24, 0x08, t_off + 4)
        d += bytes(hdr24)
        struct.pack_into("<q", d, hdr, new_off)
        struct.pack_into("<i", d, hdr + 0x20, evcnt + 1)
        struct.pack_into("<i", d, 0x0C, len(d))          # TAE file size

        # EventGroup values are ABSOLUTE event-header offsets (TAE3.cs: the reader maps
        # each stored offset to an index via eventHeaderOffsets.FindIndex).  Since the
        # header array just moved, rewrite every value that pointed at the old array,
        # otherwise the lookup returns -1 and the game crashes on load.
        groups_off = i64(hdr + 0x08)
        groups_cnt = i32(hdr + 0x24)
        fixed = 0
        for gi in range(max(0, groups_cnt)):
            g = groups_off + gi * 32
            n = i64(g)
            voff = i64(g + 8)
            if n <= 0 or voff <= 0:
                continue
            for k in range(n):
                p = voff + k * 4
                val = struct.unpack_from("<i", d, p)[0]
                idx = val - evoff
                if 0 <= idx < evcnt and val == evoff + idx * 24:
                    struct.pack_into("<i", d, p, new_off + idx * 24)
                    fixed += 1
        changed.append((aid, evcnt + 1, fixed))
    return bytes(d), changed


def rebuild_bnd4(data, patches):
    """Grow the BND4 without disturbing anything else.

    Every untouched entry keeps its ORIGINAL dataOffset, so the original layout
    (including the 16-byte alignment padding between data blocks) is preserved
    byte for byte.  Patched entries are appended at the end of the file and only
    their own record (size + dataOffset) is rewritten.  With an empty patch list
    this is the identity transform.
    """
    ents = B.entries(data)
    hdr = struct.unpack_from("<q", data, 0x20)[0]
    pdata = {i: nd for i, osz, nd in patches}

    out = bytearray(data)
    for i, (name, off, size, flags, fid) in enumerate(ents):
        blob = pdata.get(i)
        if blob is None:
            continue
        rec = 0x40 + i * hdr
        new_off = len(out)
        out += blob
        struct.pack_into("<Q", out, rec + 0x08, len(blob))
        struct.pack_into("<Q", out, rec + 0x10, len(blob))
        struct.pack_into("<I", out, rec + 0x18, new_off)
    return bytes(out)


def recompress_dcx(original_dcx, new_payload):
    """Keep the original DCX header, swap in a fresh zlib stream and fix size fields."""
    hdr = bytearray(original_dcx[:0x24])
    comp = zlib.compress(new_payload, 9)
    # DCX/DFLT: the two 32-bit fields at 0x08/0x0C hold uncompressed/compressed sizes,
    # and the DCS header repeats them.  Patch every plausible location.
    unc = len(new_payload)
    for off in (0x08, 0x0C):
        pass
    out = bytearray()
    out += hdr
    out += comp
    # search-and-replace the original sizes with the new ones inside the small header
    orig_unc = struct.unpack_from("<I", original_dcx, 0x1C)[0] if len(original_dcx) > 0x20 else 0
    return bytes(out), unc, len(comp)


def main():
    inp, outp, idfile = sys.argv[1], sys.argv[2], sys.argv[3]
    param = bytes.fromhex(sys.argv[sys.argv.index("--param") + 1]) if "--param" in sys.argv else bytes([1, 0, 0, 0])
    dry = "--dry" in sys.argv
    max_n = int(sys.argv[sys.argv.index("--max") + 1], 0) if "--max" in sys.argv else 10 ** 9
    targets = set(load_ids(idfile))
    if "--only" in sys.argv:
        targets = {int(sys.argv[sys.argv.index("--only") + 1], 0)}
    print("target animation ids: %d   params=%s   dry=%s" % (len(targets), param.hex(" "), dry))

    data = B.load(inp)
    ents = B.entries(data)
    patches = []
    total = 0
    for i, (name, off, size, flags, fid) in enumerate(ents):
        base = os.path.basename(name)
        if not base.lower().endswith(".tae") or size == 0:
            continue
        tae = data[off:off + size]
        if len(tae) < 0x40 or tae[:4] != b"TAE ":
            continue
        new_tae, changed = patch_one_tae(tae, targets, param, max_n)
        if changed:
            delta = len(new_tae) - size
            print("  %-12s +%d byte(s) for %d animation(s): %s" %
                  (base, delta, len(changed),
                   ", ".join("%d->%d ev (%d group refs)" % c for c in changed[:6])))
            patches.append((i, size, new_tae))
            total += len(changed)
    print("animations patched: %d   TAE files touched: %d" % (total, len(patches)))
    if dry or not patches:
        print("(dry run, nothing written)")
        return 0

    new_bnd = rebuild_bnd4(data, patches)
    print("rebuild: %d -> %d bytes" % (len(data), len(new_bnd)))
    original_dcx = open(inp, "rb").read()
    comp = zlib.compress(new_bnd, 9)
    # DCX layout: [0x00 "DCX\0" ...][0x18 "DCS\0"][0x1C BE uncompressed][0x20 BE compressed]
    #             [0x24 "DCP\0"][0x28 "DFLT"][... 0x4C][zlib stream]
    out = bytearray(original_dcx[:0x4C])
    struct.pack_into(">I", out, 0x1C, len(new_bnd))
    struct.pack_into(">I", out, 0x20, len(comp))
    out += comp
    with open(outp, "wb") as fh:
        fh.write(out)
    print("wrote %s (%d bytes, payload %d, zlib %d)" % (outp, len(out), len(new_bnd), len(comp)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
