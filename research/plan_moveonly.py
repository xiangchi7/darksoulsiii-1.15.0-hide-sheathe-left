#!/usr/bin/env python3
"""Can we get a STRICTLY player-only mod by only moving dummies in the player's model?

The parameter table is shared by PC and NPCs, so it can never hold two different
values.  But the *model* is per character.  If we move the very dummies that the
vanilla `leftHang_*` fields already point at, far away inside the PLAYER's model
only, then:

  * the player's sheathed left item is drawn 1 km below  -> hidden
  * NPCs keep their own (untouched) dummies and parameters -> completely vanilla
  * no parameter is written at all -> no scan/reload problems either

The catch: a dummy id can be shared between "left sheathed" and other slots, and
moving it moves ALL of those uses for the player.  This script classifies every id
used by leftHang_* into:

  CLEAN     - used only by leftHang_*            -> moving it is free
  SECONDARY - also used by models 1..3 of some slot (spare blade / scabbard /
              extra blade in two-hand)          -> moving it also hides those
  BLOCKED   - also used by a primary field (left_0/right_0/both_0/rightHang_*)
              -> moving it would break the weapon in hand / the right sheath

usage: py plan_moveonly.py <vanilla.json>
"""

import json
import sys
from collections import defaultdict

PRIMARY = ["left_0", "right_0", "both_0", "leftBoth_0",
           "rightHang_0", "rightHang_1", "rightHang_2", "rightHang_3"]
SECONDARY = ["left_1", "left_2", "left_3", "right_1", "right_2", "right_3",
             "both_1", "both_2", "both_3", "leftBoth_1", "leftBoth_2", "leftBoth_3"]
LEFTHANG = ["leftHang_0", "leftHang_1", "leftHang_2", "leftHang_3"]


def main():
    rows = {int(k): v["copy0"]["vals"] for k, v in json.load(open(sys.argv[1], encoding="utf-8")).items()}

    lh_left = defaultdict(list)      # id -> [(row, field)]  (what we want hidden)
    other = defaultdict(lambda: defaultdict(list))   # id -> field -> [(row, field)]

    for rid, v in rows.items():
        for f in LEFTHANG:
            if v.get(f, 0):
                lh_left[v[f]].append((rid, f))
        for f, val in v.items():
            if f in LEFTHANG or not isinstance(val, int) or val <= 0:
                continue
            other[val][f].append((rid, f))

    clean, secondary, blocked = [], [], []
    for i in sorted(lh_left):
        fields = other.get(i, {})
        prim = {f: len(v) for f, v in fields.items() if f in PRIMARY}
        sec = {f: len(v) for f, v in fields.items() if f in SECONDARY}
        unk = {f: len(v) for f, v in fields.items() if f not in PRIMARY and f not in SECONDARY}
        rec = (i, len(lh_left[i]), sorted(lh_left[i]), prim, sec, unk)
        if prim or unk:
            blocked.append(rec)
        elif sec:
            secondary.append(rec)
        else:
            clean.append(rec)

    def show(title, items):
        print("\n=== %s (%d ids) ===" % (title, len(items)))
        for i, n, uses, prim, sec, unk in items:
            extra = ""
            if prim:
                extra += "  PRIMARY: " + ", ".join("%s x%d" % kv for kv in sorted(prim.items()))
            if unk:
                extra += "  OTHER: " + ", ".join("%s x%d" % kv for kv in sorted(unk.items()))
            if sec:
                extra += "  extra-models: " + ", ".join("%s x%d" % kv for kv in sorted(sec.items()))
            print("  id %-5d leftHang x%-3d (rows %s)%s" % (i, n, ",".join(str(r) for r, _ in uses[:6]) + ("..." if len(uses) > 6 else ""), extra))

    show("CLEAN - safe to move", clean)
    show("SECONDARY - moving also hides extra models (spare blade / scabbard)", secondary)
    show("BLOCKED - cannot move (would break in-hand / right sheath)", blocked)

    total_lh = sum(len(v) for v in lh_left.values())
    covered = sum(n for _, n, *_ in clean + secondary)
    print("\ncoverage: %d of %d leftHang field-uses can be hidden this way (%.0f%%), %d row(s)/field(s) would stay visible"
          % (covered, total_lh, 100.0 * covered / total_lh, total_lh - covered))
    if blocked:
        rows_hit = sorted({r for _, _, uses, *_ in blocked for r, _ in uses})
        print("rows that would NOT be hidden if we skip the blocked ids: %s" % rows_hit)


if __name__ == "__main__":
    main()
