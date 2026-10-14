#!/usr/bin/env python3
"""Dump every HideEquippedWeapon (710) event of a DS3 anibnd with its times,
and report the evidence that decides whether the flag is persistent or windowed.

usage: py dump710.py <cXXXX.anibnd.dcx> [--sequences] [--list]
"""

import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3bnd as B  # noqa: E402
import diff710 as D  # noqa: E402


def collect(path, event_id=710, with_times=True):
    data = B.load(path)
    ents = B.entries(data)
    res = {}
    for name, off, size, flags, fid in ents:
        if not name.lower().endswith(".tae"):
            continue
        short = os.path.basename(name.replace("\\", "/"))
        parsed = D.parse_tae(data, off, event_id)
        if parsed:
            res[short] = parsed
    return res


def main():
    path = sys.argv[1]
    data = collect(path)

    # 1. all events, with times
    all_evs = []          # (tae, anim, start, end, params)
    for tae, anims in data.items():
        for aid, evs in anims.items():
            for (s, e, p) in evs:
                all_evs.append((tae, aid, s, e, p))
    print("total 710 events: %d in %d TAE files" % (len(all_evs), len(data)))

    # 2. time structure
    exact0 = sum(1 for *_, s, e, p in [(0, 0, 0, a, b, c) for a, b, c in []] )  # placeholder
    start0 = sum(1 for (_, _, s, _, _) in all_evs if s == 0.0)
    end0 = sum(1 for (_, _, _, e, _) in all_evs if e == 0.0)
    end_eq_start = sum(1 for (_, _, s, e, _) in all_evs if e == s)
    print("start==0: %d   end==0: %d   end==start: %d" % (start0, end0, end_eq_start))
    print("start time histogram: %s" % Counter(round(s, 2) for _, _, s, _, _ in all_evs).most_common(8))
    print("end   time histogram: %s" % Counter(round(e, 2) for _, _, _, e, _ in all_evs).most_common(8))

    # 3. animations with several 710 events -> do they clear flags again?
    multi = {}
    for tae, anims in data.items():
        for aid, evs in anims.items():
            if len(evs) > 1:
                multi[(tae, aid)] = sorted(evs, key=lambda x: x[0])
    print("\nanimations with >1 event 710: %d" % len(multi))
    if "--sequences" in sys.argv or True:
        for (tae, aid), evs in sorted(multi.items())[:25]:
            print("  %-12s anim %-7d %s" % (tae, aid,
                  "  ".join("%s@%s-%s" % (p.hex(" "), s, e) for s, e, p in evs)))

    # 4. does any event clear a flag that another event in the same anim set?
    combos = Counter()
    for tae, anims in data.items():
        for aid, evs in anims.items():
            combos[tuple(sorted(p.hex(" ") for _, _, p in evs))] += 1
    print("\nparams combos per animation (top 12):")
    for k, v in combos.most_common(12):
        print("   %-40s %d" % (" | ".join(k) if k else "(none)", v))

    # 5. which animations use left-hand-only, and where
    print("\nanimations with a left-hand-only (01 00 00 00) event:")
    n = 0
    for tae, anims in sorted(data.items()):
        for aid, evs in sorted(anims.items()):
            if any(p[:1] == b"\x01" and p[1:2] == b"\x00" for _, _, p in evs):
                print("  %-12s anim %-7d %s" % (tae, aid,
                      "  ".join("%s@%s-%s" % (p.hex(" "), s, e) for s, e, p in evs)))
                n += 1
                if n > 40:
                    break
        if n > 40:
            break

    # 6. category histogram of "01 01 00 00" events (which sets use both-hand hide)
    cats = Counter()
    for (tae, aid, s, e, p) in all_evs:
        if p.hex(" ") == "01 01 00 00":
            cats[tae] += 1
    print("\nTAE files with 01 01 00 00 events: %s" % cats.most_common(15))


if __name__ == "__main__":
    main()
