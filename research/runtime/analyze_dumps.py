#!/usr/bin/env python3
"""Compare two dumpwep.py dumps and classify the vanilla attach values.

usage: py analyze_dumps.py <vanilla.json> <active.json> [dummies.txt] [bone-table.txt]
"""

import json
import re
import sys
from collections import Counter


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    out = {}
    for rid, rec in d.items():
        out[int(rid)] = rec["copy0"]["vals"]
    return out


def dummy_ids(path):
    ids = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = re.match(r"\s*dummy\s+(-?\d+)\s", line)
        if m:
            ids.append(int(m.group(1)))
    return ids


def bone_names(path):
    names = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = re.match(r"\s*(\d+)\s+(\S.*?)\s*$", line)
        if m:
            names[int(m.group(1))] = m.group(2).strip()
    return names


FIELDS = ["leftHang_0", "leftHang_1", "leftHang_2", "leftHang_3",
          "rightHang_0", "right_1", "right_2", "right_3",
          "left_0", "left_1", "both_0", "leftBoth_0"]


def main():
    van = load(sys.argv[1])
    act = load(sys.argv[2])
    dummies = dummy_ids(sys.argv[3]) if len(sys.argv) > 3 else []
    bones = bone_names(sys.argv[4]) if len(sys.argv) > 4 else {}
    dummy_set = set(dummies)

    print("rows: vanilla=%d active=%d" % (len(van), len(act)))

    diff_rows = [r for r in sorted(van) if van[r] != act.get(r)]
    diff_fields = Counter()
    for r in diff_rows:
        for f in van[r]:
            if van[r][f] != act[r][f]:
                diff_fields[f] += 1
    print("rows changed by the mod: %d" % len(diff_rows))
    print("changed fields: %s" % dict(diff_fields))

    print("\nvanilla value distributions")
    for f in FIELDS:
        c = Counter(van[r][f] for r in van)
        vals = sorted(c)
        print("  %-12s distinct=%-3d min=%-5d max=%-6d top=%s"
              % (f, len(vals), min(vals), max(vals), c.most_common(6)))

    allvals = sorted({van[r][f] for r in van for f in FIELDS})
    print("\nall distinct vanilla values: %s" % allvals)
    print("max value = %d" % max(allvals))
    print("exists as bone index (<136)? %s" % [v for v in allvals if v > 135])
    if dummy_set:
        missing = [v for v in allvals if v >= 0 and v not in dummy_set]
        print("dummy ReferenceIDs in c0000.flver: %d distinct" % len(dummy_set))
        print("values with NO matching dummy ReferenceID: %s" % missing)
        print("values WITH a matching dummy ReferenceID: %s"
              % [v for v in allvals if v in dummy_set])
    if bones:
        print("\nvalue -> bone name (skeleton table) for the distinct values")
        for v in allvals:
            print("  %-5d %s" % (v, bones.get(v, "(no such bone name)")))

    print("\nper-row vanilla leftHang_0..3 / right_1..3 (non-zero rows only)")
    for r in sorted(van):
        v = van[r]
        if any(v[f] for f in ("leftHang_0", "leftHang_1", "leftHang_2", "leftHang_3",
                              "right_1", "right_2", "right_3")):
            print("  id=%-5d LHang=%s,%s,%s,%s  R1..3=%s,%s,%s  left0=%s both0=%s"
                  % (r, v["leftHang_0"], v["leftHang_1"], v["leftHang_2"], v["leftHang_3"],
                     v["right_1"], v["right_2"], v["right_3"], v["left_0"], v["both_0"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
