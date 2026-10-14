#!/usr/bin/env python3
"""Scan a live process for a byte pattern and report where it is found.

usage: py findbytes.py <hexpattern> [--utf16] [--max N] [--context BYTES]
       py findbytes.py --ptr <hexValue> [--max N] [--context BYTES]

  --utf16     expand the pattern to UTF-16LE (for asset path strings)
  --ptr       search for an 8-byte little-endian value (a pointer)
  --context   dump this many bytes around each hit
"""

import ctypes
import ctypes.wintypes as wt
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3probe as P  # noqa: E402

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
CHUNK = 1 << 22


k32.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQuery.restype = ctypes.c_size_t


def regions():
    addr = 0x10000
    maxaddr = 0x7FFFFFFF0000
    mbi = MBI()
    while addr < maxaddr:
        if not k32.VirtualQuery(ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if (mbi.State == MEM_COMMIT and mbi.Type in (MEM_PRIVATE, MEM_MAPPED)
                and not (mbi.Protect & PAGE_GUARD) and not (mbi.Protect & PAGE_NOACCESS)):
            yield base, size
        if not size:
            break
        addr = base + size


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--ptr":
        value = int(args[1], 0)
        pat = struct.pack("<Q", value)
    else:
        pat = bytes.fromhex(args[0].replace(" ", ""))
        if "--utf16" in args:
            pat = b"".join(bytes([c, 0]) for c in pat)
    maxhits = 20
    if "--max" in args:
        maxhits = int(args[args.index("--max") + 1], 0)
    context = 0
    if "--context" in args:
        context = int(args[args.index("--context") + 1], 0)

    g = P.Game()
    print("pid=%d pattern=%s (%d bytes)" % (g.pid, pat.hex(" "), len(pat)), flush=True)
    hits = 0
    scanned = 0
    try:
        for base, size in regions():
            off = 0
            while off < size:
                n = min(CHUNK + len(pat), size - off)
                data = g.read(base + off, n)
                if data:
                    scanned += len(data)
                    pos = 0
                    while True:
                        i = data.find(pat, pos)
                        if i < 0:
                            break
                        addr = base + off + i
                        print("  hit 0x%X" % addr, flush=True)
                        if context:
                            blob = g.read(addr - context, context * 2)
                            if blob:
                                for k in range(0, len(blob), 16):
                                    chunk = blob[k:k + 16]
                                    print("     %+06X  %-47s  %s" %
                                          (k - context, chunk.hex(" "),
                                           "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)),
                                          flush=True)
                        hits += 1
                        if hits >= maxhits:
                            print("  (limit)"); return 0
                        pos = i + 1
                off += CHUNK
    finally:
        g.close()
    print("  %d hit(s), %.0f MB scanned" % (hits, scanned / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
