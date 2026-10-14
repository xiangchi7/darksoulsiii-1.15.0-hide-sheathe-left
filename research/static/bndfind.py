#!/usr/bin/env python3
"""Locate the inner files of a DS3 BND4 (after DCX decompression) and dump the
record that owns a given file name.

usage: py bndfind.py <bundle> [name-substring]
"""

import os
import struct
import sys
import zlib


def read_dcx(path):
    data = open(path, "rb").read()
    if data[:4] != b"DCX\x00":
        return data
    for magic in (b"\x78\xda", b"\x78\x9c", b"\x78\x01", b"\x78\x5e"):
        i = data.find(magic, 0x24)
        if i >= 0:
            d = zlib.decompressobj()
            out = d.decompress(data[i:])
            try:
                out += d.flush()
            except Exception:
                pass
            return out
    raise SystemExit("no zlib stream")


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def i32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def main():
    path = sys.argv[1]
    want = sys.argv[2].lower() if len(sys.argv) > 2 else ".tae"
    data = read_dcx(path)
    print("%s -> %d bytes, magic=%r files=%d" % (os.path.basename(path), len(data),
                                                 data[:4], i32(data, 0x0C)))
    count = i32(data, 0x0C)
    hdr_size = struct.unpack_from("<q", data, 0x20)[0]
    first_hdr = 0x40
    print("count=%d hdrSize=0x%X guess firstHdr=0x%X  (headers end ~0x%X)" %
          (count, hdr_size, first_hdr, first_hdr + count * hdr_size))

    # find UTF-16 file names
    names = []
    for enc, tag in (("utf-16-le", "u16"), ("latin1", "a")):
        pat = want.encode(enc) if enc.startswith("utf-16") else want.encode("latin1")
        pos = 0
        while True:
            i = data.find(pat, pos)
            if i < 0:
                break
            # walk back to the start of the string
            s = i
            while s >= 2 and data[s - 2:s] != b"\x00\x00" and (i - s) < 200:
                s -= 2 if enc.startswith("utf-16") else 1
            end = data.find(b"\x00\x00", i)
            raw = data[s:end + 2] if end > 0 else data[s:i + 40]
            try:
                nm = raw.decode("utf-16-le", "ignore").rstrip("\x00") if enc.startswith("utf-16") else raw.decode("latin1", "ignore")
            except Exception:
                nm = "?"
            if nm and (nm.lower().endswith(want) or want in nm.lower()):
                names.append((s, nm))
            pos = i + 2
    seen = set()
    print("\nfound %d name hit(s):" % len(names))
    for off, nm in names[:40]:
        if nm in seen:
            continue
        seen.add(nm)
        print("  name@0x%-8X %r" % (off, nm))
        # search the header block for this name offset
        needle = struct.pack("<I", off)
        p = first_hdr
        while p < min(len(data), first_hdr + count * 0x30):
            if data[p:p + 4] == needle:
                rec = p - 0x18
                if rec >= 0:
                    flags = u32(data, rec)
                    rid = i32(data, rec + 4)
                    size = struct.unpack_from("<q", data, rec + 8)[0]
                    dataoff = struct.unpack_from("<q", data, rec + 0x10)[0]
                    print("     record@0x%X flags=0x%X id=%d size=%d dataOff=0x%X (fileOffsetField@0x%X)" %
                          (rec, flags, rid, size, dataoff, p))
                    if 0 < dataoff < len(data) - 4:
                        print("     data magic: %r" % data[dataoff:dataoff + 4])
                break
            p += 1
    if len(names) > 40:
        print("  ... (%d more)" % (len(names) - 40))
    return 0


if __name__ == "__main__":
    sys.exit(main())
