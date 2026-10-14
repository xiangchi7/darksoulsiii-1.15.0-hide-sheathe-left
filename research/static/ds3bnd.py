#!/usr/bin/env python3
"""DS3 BND4 tool (handles the DCX wrapper): list, extract, find, dump.

usage:
  py ds3bnd.py <bundle> list
  py ds3bnd.py <bundle> find <u32>
  py ds3bnd.py <bundle> dump <nameSubstring> <relOffset> <len>
  py ds3bnd.py <bundle> extract <nameSubstring> <outfile>
"""

import os
import struct
import sys
import zlib


def load(path):
    data = open(path, "rb").read()
    if data[:4] == b"DCX\x00":
        for m in (b"\x78\xda", b"\x78\x9c", b"\x78\x01", b"\x78\x5e"):
            i = data.find(m, 0x24)
            if i >= 0:
                d = zlib.decompressobj()
                out = d.decompress(data[i:])
                try:
                    out += d.flush()
                except Exception:
                    pass
                return out
        raise SystemExit("no zlib stream")
    return data


def entries(data):
    count = struct.unpack_from("<i", data, 0x0C)[0]
    hdr = struct.unpack_from("<q", data, 0x20)[0]
    out = []
    for i in range(count):
        rec = 0x40 + i * hdr
        if rec + hdr > len(data) or hdr <= 0:
            break
        flags = struct.unpack_from("<I", data, rec)[0]
        fid = struct.unpack_from("<i", data, rec + 4)[0]
        size = struct.unpack_from("<Q", data, rec + 8)[0]
        off = struct.unpack_from("<I", data, rec + 0x18)[0]
        noff = struct.unpack_from("<I", data, rec + 0x20)[0]
        name = ""
        if 0 < noff < len(data):
            e = data.find(b"\x00\x00", noff)
            try:
                name = data[noff:e + 1].decode("utf-16-le", "ignore").rstrip("\x00")
            except Exception:
                pass
        out.append((name, off, size, flags, fid))
    return out


def main():
    path = sys.argv[1]
    cmd = sys.argv[2] if len(sys.argv) > 2 else "list"
    data = load(path)
    ents = entries(data)
    print("%s -> %d bytes, %d entries" % (os.path.basename(path), len(data), len(ents)))

    if cmd == "list":
        for i, (name, off, size, flags, fid) in enumerate(ents[:40]):
            print("  [%3d] off=0x%-9X size=%-9d flags=0x%02X id=%d  %s" %
                  (i, off, size, flags, fid, os.path.basename(name)))
        if len(ents) > 40:
            print("  ... (%d more)" % (len(ents) - 40))
        return 0

    want = sys.argv[3].lower() if len(sys.argv) > 4 else ""
    sel = [(i, n, o, s, f, fid) for i, (n, o, s, f, fid) in enumerate(ents) if want in n.lower()]
    if not sel:
        print("no entry matches %r" % want)
        return 1
    i, name, off, size, flags, fid = sel[0]
    print("  entry [%d] %s  off=0x%X size=%d magic=%r" %
          (i, os.path.basename(name), off, size, data[off:off + 4]))

    if cmd == "find":
        val = int(sys.argv[4], 0)
        needle = struct.pack("<I", val)
        blob = data[off:off + size]
        hits = []
        p = 0
        while True:
            j = blob.find(needle, p)
            if j < 0:
                break
            hits.append(j)
            p = j + 1
        print("  %d occurrence(s) of %d in this entry" % (len(hits), val))
        for h in hits[:20]:
            print("     +0x%X" % h)
        if hits:
            h0 = hits[0]
            print("  --- bytes around the first hit (entry+0x%X) ---" % h0)
            base = max(0, h0 - 0x40)
            for k in range(base, min(size, h0 + 0x40), 16):
                chunk = data[off + k:off + k + 16]
                print("  +%06X  %-47s  %s" % (k, chunk.hex(" "),
                                              "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)))
    elif cmd == "dump":
        ro = int(sys.argv[4], 0)
        ln = int(sys.argv[5], 0)
        for k in range(ro, ro + ln, 16):
            chunk = data[off + k:off + k + 16]
            print("  +%06X  %-47s  %s" % (k, chunk.hex(" "),
                                          "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)))
    elif cmd == "extract":
        out = sys.argv[4]
        with open(out, "wb") as fh:
            fh.write(data[off:off + size])
        print("  wrote %s (%d bytes)" % (out, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
