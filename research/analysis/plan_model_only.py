#!/usr/bin/env python3
"""Plan a model-only variant of the mod.

Idea: instead of writing a parking dummy id into the shared parameter table (which
PC and NPC share), move the dummies that the vanilla `leftHang_*` fields already
point at, inside the PLAYER's model only.  NPCs keep their own (untouched) model,
so nothing changes for them and no parameter is ever written.

This script answers the two questions that decide whether that works:

  1. for every dummy id used by `leftHang_*`, is it ALSO used by any other
     dummy-poly field of any row (in-hand position, right-hand hang, ...)?
     If yes, moving it would break that other use.
  2. the same for the paired-weapon fields `right_1..3`.

usage: py plan_model_only.py <vanilla.json>
"""

import json
import sys
from collections import Counter, defaultdict

GROUPS = {
    "leftHang": ["leftHang_0", "leftHang_1", "leftHang_2", "leftHang_3"],
    "rightHang": ["rightHang_0", "rightHang_1", "rightHang_2", "rightHang_3"],
    "right_1..3": ["right_1", "right_2", "right_3"],
    "left_1..3": ["left_1", "left_2", "left_3"],
    "left_inhand": ["left_0", "left_1", "left_2", "left_3"],
    "right_inhand": ["right_0", "right_1", "right_2", "right_3"],
    "both_inhand": ["both_0", "both_1", "both_2", "both_3"],
    "leftBoth": ["leftBoth_0", "leftBoth_1", "leftBoth_2", "leftBoth_3"],
}


def main():
    rows = {int(k): v["copy0"]["vals"] for k, v in json.load(open(sys.argv[1], encoding="utf-8")).items()}

    # which ids each group uses, and where
    uses = defaultdict(lambda: defaultdict(list))   # id -> group -> [(row, field)]
    for rid, v in rows.items():
        for g, fields in GROUPS.items():
            for f in fields:
                val = v.get(f, 0)
                if val:
                    uses[val][g].append((rid, f))

    def report(target_group, label):
        print("\n=== %s ===" % label)
        movable, conflict = [], []
        for i in sorted(uses):
            u = uses[i]
            if target_group not in u:
                continue
            others = {g: len(v) for g, v in u.items() if g != target_group}
            n_target = len(u[target_group])
            if others:
                conflict.append((i, n_target, others))
            else:
                movable.append((i, n_target))
        print("safely movable (only used by %s): %s" % (target_group,
              ", ".join("%d(x%d)" % (i, n) for i, n in movable) or "(none)"))
        print("conflicting (also used elsewhere):")
        for i, n, others in conflict:
            detail = ", ".join("%s x%d" % (g, c) for g, c in sorted(others.items()))
            print("   id %-5d %s x%-3d  also: %s" % (i, target_group, n, detail))
            for g in others:
                for rid, f in uses[i][g][:4]:
                    print("        row %-5d %s" % (rid, f))
        return movable, conflict

    lh_move, lh_conf = report("leftHang", "leftHang_* (the main effect)")
    r_move, r_conf = report("right_1..3", "right_1..3 (paired weapons)")

    # how many rows would keep needing a parameter write if we move the safe ids?
    print("\n=== rows that would still need a param write for the left-hang effect ===")
    need = []
    for rid, v in sorted(rows.items()):
        hit = [f for f in GROUPS["leftHang"] if v.get(f, 0) and any(v[f] == i for i, _ in lh_conf)]
        if hit:
            need.append((rid, hit, [v[f] for f in hit]))
    print("rows: %d" % len(need))
    for rid, hit, vals in need:
        print("   row %-5d %s = %s" % (rid, ",".join(hit), vals))

    print("\n=== distinct ids in each group (for reference) ===")
    for g, fields in GROUPS.items():
        s = sorted({rows[r].get(f, 0) for r in rows for f in fields} - {0})
        print("  %-12s %s" % (g, s))


if __name__ == "__main__":
    main()
