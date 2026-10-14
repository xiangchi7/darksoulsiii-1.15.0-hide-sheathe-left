#!/usr/bin/env python3
"""Is there a dummy id that (a) every character model has and (b) no param field uses?

If yes, the NPC side-effect can be made artifact-free without touching any
character model: write that id into the shared parameter table, and move it far
away inside the PLAYER's model only.  NPCs then resolve a *valid* dummy (no NaN /
black triangles) at its normal position.

usage: py plan_common_id.py <chrids.tsv> <vanilla.json> [dummies.txt]
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

    rows = {int(k): v["copy0"]["vals"] for k, v in json.load(open(sys.argv[2], encoding="utf-8")).items()}
    used_by_params = defaultdict(set)
    for rid, v in rows.items():
        for f, val in v.items():
            if isinstance(val, int) and val > 0:
                used_by_params[val].add(f)

    print("models: %d" % len(per_file))
    common = set.intersection(*per_file.values()) if per_file else set()
    print("ids present in EVERY model: %d  ->  %s" % (len(common), sorted(common)))

    free = sorted(i for i in common if i not in used_by_params)
    print("\nof those, ids NEVER referenced by any WepAbsorpPosParam field: %s" % (free or "(none)"))
    for i in sorted(common):
        where = sorted(used_by_params.get(i, []))
        print("   id %-5d in all %d models   param fields: %s" % (i, len(per_file), ", ".join(where) if where else "-- free --"))

    if len(sys.argv) > 3 and free:
        pos = {}
        for line in open(sys.argv[3], encoding="utf-8", errors="ignore"):
            m = re.match(r"\s*dummy\s+(-?\d+)\s+bone\[\s*(-?\d+)\]\s+(\S+)\s+pos=\(\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\)", line)
            if m:
                pos.setdefault(int(m.group(1)), (m.group(3), float(m.group(4)), float(m.group(5)), float(m.group(6))))
        print("\npositions of the free ids inside the PLAYER's model (what an NPC would show):")
        for i in free:
            p = pos.get(i)
            print("   id %-5d %s" % (i, "(not in c0000)" if not p else "bone %s at (%s, %s, %s)  |p|=%.2f" % p))


if __name__ == "__main__":
    main()
