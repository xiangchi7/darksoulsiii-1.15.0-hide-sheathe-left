#!/usr/bin/env python3
"""Compare two wide snapshots and report the differences, grouped.

usage: py abdiff.py <A.bin> <B.bin>
"""

import os
import struct
import sys


def load(path):
    with open(path, "rb") as fh:
        base, n = struct.unpack("<QI", fh.read(12))
        data = fh.read()
    return base, data


def is_ptr(v):
    return 0x7FF000000000 <= v <= 0x7FFFFFFFFFFF


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    A_base, A = load(a_path)
    B_base, B = load(b_path)
    n = min(len(A), len(B))
    print("A=%s base=0x%X   B=%s base=0x%X   compare=%d MB" %
          (os.path.basename(a_path), A_base, os.path.basename(b_path), B_base, n >> 20))

    diffs = []
    off = 0
    while off + 4 <= n:
        if A[off:off + 4] != B[off:off + 4]:
            va = struct.unpack_from("<I", A, off)[0]
            vb = struct.unpack_from("<I", B, off)[0]
            diffs.append((A_base + off, va, vb))
        off += 4
    print("total differing words: %d" % len(diffs))

    print("")
    print("--- item-id-like values (900k..200M) ---")
    c = 0
    for addr, va, vb in diffs:
        if 900000 <= va <= 200000000 or 900000 <= vb <= 200000000:
            print("  0x%X  %12d -> %-12d  0x%08X -> 0x%08X" % (addr, va, vb, va, vb))
            c += 1
            if c >= 50:
                print("  ... (more)")
                break

    print("")
    print("--- 8-byte aligned pointer changes ---")
    byaddr = {addr: (va, vb) for addr, va, vb in diffs}
    c = 0
    for addr, va, vb in diffs:
        if addr % 8:
            continue
        if is_ptr(va) or is_ptr(vb):
            lo = byaddr.get(addr + 4, (0, 0))
            old = (lo[0] << 32) | va
            new = (lo[1] << 32) | vb
            print("  0x%X  0x%012X -> 0x%012X" % (addr, old, new))
            c += 1
            if c >= 40:
                print("  ... (more)")
                break

    regions = [(0x7FF4A8000000, 0x7FF4AC000000, "attach/model area (ChrAsm)"),
               (0x7FF4AD000000, 0x7FF4AE000000, "equipment area"),
               (0x7FF49E000000, 0x7FF49F000000, "GameData/save area"),
               (0x7FF4B0000000, 0x7FF4C0000000, "other heap")]
    for lo, hi, name in regions:
        sel = [d for d in diffs if lo <= d[0] < hi]
        print("")
        print("--- %s 0x%X..0x%X : %d diff(s) ---" % (name, lo, hi, len(sel)))
        for addr, va, vb in sel[:25]:
            print("  0x%X  %12d -> %-12d  0x%08X -> 0x%08X" % (addr, va, vb, va, vb))
        if len(sel) > 25:
            print("  ... (%d more)" % (len(sel) - 25))
    return 0


if __name__ == "__main__":
    sys.exit(main())
