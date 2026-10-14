#!/usr/bin/env python3
"""Coverage analysis: which dummy ids are present in (almost) every character model,
and which ids are never referenced by any WepAbsorpPosParam field.

usage: py plan_common_id2.py <chrids.tsv> <vanilla.json> [dummies.txt] [minCoverage]
"""

import json
import re
import sys
from collections import defaultdict


def main():
    per_file = {}
    for line in open(sys.argv[1], encoding="utf-8", errors="ignore"):
        if "\t" not in line:
            continue
        name, ids = line.rstrip("\n").split("\t", 1)
        per_file[name] = set(int(x) for x in ids.split(",") if x)
    total = len(per_file)

    rows = {int(k): v["copy0"]["vals"] for k, v in json.load(open(sys.argv[2], encoding="utf-8")).items()}
    used = defaultdict(set)
    for rid, v in rows.items():
        for f, val in v.items():
            if isinstance(val, int) and val > 0:
                used[val].add(f)

    coverage = defaultdict(list)
    for name, ids in per_file.items():
        for i in ids:
            coverage[i].append(name)

    min_cov = int(sys.argv[4]) if len(sys.argv) > 4 else total - 5
    print("models: %d ; ids with coverage >= %d and NOT used by any param field:" % (total, min_cov))
    cands = []
    for i, files in coverage.items():
        if len(files) >= min_cov and i not in used:
            cands.append((len(files), i, sorted(set(per_file) - set(files))))
    for cov, i, missing in sorted(cands, reverse=True)[:15]:
        print("   id %-5d %d/%d models   missing: %s" % (i, cov, total, ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "")))
    if not cands:
        print("   (none)")

    print("\nbest coverage among ids that are free (regardless of coverage):")
    free = [(len(files), i) for i, files in coverage.items() if i not in used]
    for cov, i in sorted(free, reverse=True)[:12]:
        print("   id %-5d %d/%d models" % (i, cov, total))

    if len(sys.argv) > 3 and cands:
        pos = {}
        for line in open(sys.argv[3], encoding="utf-8", errors="ignore"):
            m = re.match(r"\s*dummy\s+(-?\d+)\s+bone\[\s*(-?\d+)\]\s+(\S+)\s+pos=\(\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\)", line)
            if m:
                pos.setdefault(int(m.group(1)), (m.group(3), float(m.group(4)), float(m.group(5)), float(m.group(6))))
        print("\npositions of the best candidates inside the PLAYER model (where an unprotected NPC would draw the item):")
        for cov, i, _ in sorted(cands, reverse=True)[:8]:
            p = pos.get(i)
            print("   id %-5d %s" % (i, "(not in c0000)" if not p else "bone %s at (%s, %s, %s)" % p))


if __name__ == "__main__":
    main()
