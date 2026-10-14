#!/usr/bin/env python3
"""Build probe spec files for the SoulsFormats-based patcher (validator/).

Reads the animation list produced earlier (docs/DSAnimStudio-编辑清单.txt) which
maps animation id -> TAE entry name -> state names, selects the two-hand stance
animations, and writes TSV specs consumed by:

    validator add <in.dcx> <out.dcx> <spec.tsv>

spec line: taeName <TAB> animId <TAB> paramsHex <TAB> start <TAB> end
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIST = os.path.join(HERE, "..", "docs", "DSAnimStudio-编辑清单.txt")
OUTDIR = os.path.join(HERE, "..", "probes")

HIDE_LEFT = "01000000"   # HideEquippedWeapon: LeftHand = 1
SHOW_ALL = "00000000"    # HideEquippedWeapon: every flag off (attempt to restore)

# 2H stance change (entering / leaving the two-hand grip)
HANDCHANGE_BOTH = [29010, 29011, 29012, 29013, 29014, 29015, 29050, 29053]
# weapon re-sheathing animations (single hand) - used for the explicit "show" event
HANDCHANGE_SINGLE = [29030, 29031, 29032, 29033, 29040, 29041, 29042, 29043,
                     29070, 29071, 29072, 29073]


def parse_list(path):
    """id -> (taeName, names)"""
    out = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3:
            continue
        try:
            aid = int(parts[0].strip())
        except ValueError:
            continue
        tae = parts[1].strip()
        names = "\t".join(parts[2:])
        out[aid] = (tae, names)
    return out


def main():
    table = parse_list(LIST)
    os.makedirs(OUTDIR, exist_ok=True)

    bothe_attacks = sorted(a for a, (t, n) in table.items()
                           if "AttackBoth" in n and a >= 33000)
    print("handchange-both ids : %s" % HANDCHANGE_BOTH)
    print("handchange-single   : %s" % HANDCHANGE_SINGLE)
    print("AttackBoth* ids     : %s" % bothe_attacks)

    def emit(fname, rows, header):
        path = os.path.join(OUTDIR, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# %s\n" % header)
            for tae, aid, pars, start, end in rows:
                fh.write("%s\t%d\t%s\t%s\t%s\n" % (tae, aid, pars, start, end))
        print("wrote %s (%d rows)" % (path, len(rows)))
        return path

    # A - control: reproduce the known-good DSAS edit (hide left while idling)
    emit("spec-A.tsv", [("a00.tae", 0, HIDE_LEFT, "0", "2.067")],
         "control: left hand hidden during the common idle (same as the DSAS edit)")

    # B - two-hand stance: hide during the stance change and the 2H attacks
    rows = []
    for aid in HANDCHANGE_BOTH + bothe_attacks:
        if aid in table:
            rows.append((table[aid][0], aid, HIDE_LEFT, "0", "999"))
        else:
            print("  !! id %d not in list" % aid)
    emit("spec-B.tsv", rows, "two-hand: hide left during stance change + AttackBoth* animations")

    # C - B plus an explicit 'show everything' event on the way back to one hand
    rows_c = list(rows)
    for aid in HANDCHANGE_SINGLE:
        if aid in table:
            rows_c.append((table[aid][0], aid, SHOW_ALL, "0", "999"))
    emit("spec-C.tsv", rows_c, "two-hand + explicit restore event in single-hand stance changes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
