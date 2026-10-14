#!/usr/bin/env python3
"""Show one row across every param-table copy in a dumpwep.py dump.

usage: py showcopies.py <dump.json> [rowId]
"""

import json
import sys


def main():
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    rid = sys.argv[2] if len(sys.argv) > 2 else "48"
    rec = data.get(rid)
    if not rec:
        print("row %s not in dump" % rid)
        return 1
    copies = sorted(k for k in rec if k.startswith("copy"))
    print("row %s, copies in dump: %d" % (rid, len(copies)))
    for c in copies:
        v = rec[c]["vals"]
        print("  %-7s addr=%-14s leftHang_0..3 = %s,%s,%s,%s   right_1..3 = %s,%s,%s"
              % (c, rec[c]["addr"], v["leftHang_0"], v["leftHang_1"], v["leftHang_2"], v["leftHang_3"],
                 v["right_1"], v["right_2"], v["right_3"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
