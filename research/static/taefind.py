#!/usr/bin/env python3
"""Scan every TAE of a DS3 animation bundle and report HideWeapon (710) events for
a set of animation ids (read from a name-id dump such as docs/TAE-animations-*.txt).

usage: py taefind.py <bundle> <idfile> [--params]
"""

import os
import re
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


def collect_ids(path):
    ids = {}
    rx = re.compile(r"^\s*(\d+)\s*=\s*\"([^\"]+)\"")
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = rx.match(line)
        if m:
            ids[int(m.group(1))] = m.group(2)
    return ids


def main():
    bundle = sys.argv[1]
    idfile = sys.argv[2]
    ids = collect_ids(idfile)
    print("watching %d animation id(s) from %s" % (len(ids), os.path.basename(idfile)))
    data = B.load(bundle)
    ents = B.entries(data)
    taes = [(n, o, s) for n, o, s, f, fid in ents if n.lower().endswith(".tae")]
    print("%d TAE entries" % len(taes))
    total = 0
    for name, off, size in taes:
        try:
            bank = i64(data, off + 0x20)
            b = off + bank
            cnt = i32(data, b + 4)
            anims = i64(data, b + 8)
        except Exception:
            continue
        for i in range(cnt):
            rec = off + anims + i * 16
            aid = i64(data, rec)
            aoff = i64(data, rec + 8)
            if aoff == 0 or aid not in ids:
                continue
            evoff = i64(data, off + aoff)
            evcnt = i32(data, off + aoff + 0x20)
            for k in range(evcnt):
                eh = off + evoff + k * 24
                do = i64(data, eh + 0x10)
                if do <= 0:
                    continue
                dd = off + do
                if u64(data, dd) != 710:
                    continue
                params = data[dd + 0x10:dd + 0x14]
                print("  %-10s anim %-6d %-34s params[%s]  (%.3f..%.3f)" %
                      (os.path.basename(name), aid, ids[aid][:34], params.hex(" "),
                       struct.unpack_from("<f", data, off + i64(data, eh))[0],
                       struct.unpack_from("<f", data, off + i64(data, eh + 8))[0]))
                total += 1
    print("total 710 events found in the watched animations: %d" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
