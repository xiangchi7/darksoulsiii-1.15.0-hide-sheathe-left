#!/usr/bin/env python3
"""Decompress a DCX file and dump/parse the BND4 inside it.

usage: py bndunpack.py <file.dcx|file.bnd> [--dump <n>] [--extract <outdir>]
"""

import os
import struct
import sys
import zlib


def read_dcx(path):
    data = open(path, "rb").read()
    if data[:4] != b"DCX\x00":
        return data, "raw"
    fmt = data[0x10:0x14]
    unc_off = 0
    # DFLT/DCP: zlib stream; DCS: deflate without header
    for magic in (b"\x78\xda", b"\x78\x9c", b"\x78\x01", b"\x78\x5e"):
        i = data.find(magic, 0x24)
        if i >= 0:
            unc_off = i
            break
    if unc_off == 0:
        raise SystemExit("no zlib stream found (dcx fmt=%r)" % fmt)
    d = zlib.decompressobj()
    out = d.decompress(data[unc_off:])
    try:
        out += d.flush()
    except Exception:
        pass
    return out, "dcx(%s)" % fmt.decode("latin1")


def parse_bnd4(data):
    if len(data) < 0x40 or data[:4] != b"BND4":
        print("  (not BND4: magic=%r)" % data[:4])
        return []
    ver = data[0x04:0x0C].decode("latin1", "ignore").rstrip("\x00")
    count = struct.unpack_from("<i", data, 0x0C)[0]
    hdr_size = struct.unpack_from("<q", data, 0x20)[0]
    hdr_off = struct.unpack_from("<i", data, 0x2C)[0]
    print("  BND4 ver=%r files=%d  hdrSize=0x%X hdrOff=0x%X" % (ver, count, hdr_size, hdr_off))
    files = []
    for i in range(count):
        p = hdr_off + i * hdr_size
        if p + hdr_size > len(data):
            break
        flags, fid = struct.unpack_from("<Bi", data, p)
        size, off = struct.unpack_from("<qq", data, p + 0x08)
        name_off = struct.unpack_from("<i", data, p + 0x14)[0]
        name = ""
        if 0 < name_off < len(data):
            end = data.find(b"\x00\x00", name_off)
            if end > 0:
                raw = data[name_off:end + 1]
                try:
                    name = raw.decode("utf-16-le", "ignore").rstrip("\x00")
                except Exception:
                    name = raw.decode("latin1", "ignore")
        files.append((i, name, off, size, flags))
    return files


def main():
    path = sys.argv[1]
    data, how = read_dcx(path)
    print("%s: %s -> %d bytes" % (os.path.basename(path), how, len(data)))
    if "--dump" in sys.argv:
        n = int(sys.argv[sys.argv.index("--dump") + 1], 0)
        for k in range(0, min(n, len(data)), 16):
            chunk = data[k:k + 16]
            print("  %06X  %-47s  %s" % (k, chunk.hex(" "),
                                         "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)))
    files = parse_bnd4(data)
    print("  %d entry/entries" % len(files))
    for i, name, off, size, flags in files[:60]:
        print("   [%3d] %-44s off=0x%-9X size=%-9d flags=0x%02X" % (i, name, off, size, flags))
    if len(files) > 60:
        print("   ... (%d more)" % (len(files) - 60))
    if "--extract" in sys.argv:
        outdir = sys.argv[sys.argv.index("--extract") + 1]
        os.makedirs(outdir, exist_ok=True)
        for i, name, off, size, flags in files:
            if not size or off + size > len(data):
                continue
            safe = os.path.basename(name) or ("entry%03d" % i)
            with open(os.path.join(outdir, "%03d_%s" % (i, safe)), "wb") as fh:
                fh.write(data[off:off + size])
        print("  extracted %d file(s) to %s" % (len(files), outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
