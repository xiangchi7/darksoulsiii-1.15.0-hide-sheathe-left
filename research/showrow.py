#!/usr/bin/env python3
"""Print selected WepAbsorpPosParam rows from a dumpwep.py dump.

usage: py showrow.py <dump.json> [rowId ...]
"""

import json
import sys

FIELDS = ["leftHang_0", "leftHang_1", "leftHang_2", "leftHang_3",
          "right_1", "right_2", "right_3", "rightHang_0", "left_0", "both_0"]


def main():
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    ids = sys.argv[2:] or sorted(data, key=int)
    print("rows in dump: %d" % len(data))
    for rid in ids:
        if rid not in data:
            print("row %s: not in dump" % rid)
            continue
        v = data[rid]["copy0"]["vals"]
        print("row %-6s %s   addr=%s" % (rid, "  ".join("%s=%s" % (f, v[f]) for f in FIELDS),
                                         data[rid]["copy0"]["addr"]))


if __name__ == "__main__":
    main()
