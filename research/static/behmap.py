#!/usr/bin/env python3
"""Build an animation-id -> state-names map from a DS3 behaviour bundle and select
the animations belonging to the two-hand stance.

usage: py behmap.py <cXXXX.behbnd.dcx> [outfile]
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3bnd as B  # noqa: E402

MARKER = re.compile(rb"a(\d{3})_(\d{6})\.hkx")

# names that indicate the two-hand stance / stance switching
WANT = ("AttackBoth", "HandChange", "HandChang", "ToBothHand", "BothHand",
        "IdleBoth", "BothHandIdle", "GuardBoth")


def build_map(data):
    """Return [(animId, setName, markerText, names, offset)] in file order."""
    out = []
    cur = []
    pos = 0
    for m in re.finditer(rb"[ -~]{3,}", data):
        tok = m.group(0)
        mk = MARKER.search(tok)
        if mk:
            out.append((int(mk.group(2)), mk.group(1).decode(), tok.decode("latin1"),
                        list(cur), m.start()))
            cur = []
        else:
            cur.append((tok.decode("latin1"), m.start()))
    return out


def main():
    path = sys.argv[1]
    outfile = sys.argv[2] if len(sys.argv) > 2 else None
    data = B.load(path)
    entries = build_map(data)
    print("%s: %d animation markers" % (os.path.basename(path), len(entries)))

    hits = []
    for aid, aset, marker, names, off in entries:
        joined = ",".join(n for n, _ in names)
        if any(w in joined for w in WANT):
            hits.append((aid, aset, joined, off))

    print("matching animations: %d" % len(hits))
    seen = set()
    for aid, aset, joined, off in hits:
        key = (aid, aset)
        if key in seen:
            continue
        seen.add(key)
        print("  id %-7d set a%-3s  %s" % (aid, aset, joined[:110]))

    if outfile:
        with open(outfile, "w", encoding="utf-8") as fh:
            for aid, aset, joined, off in hits:
                fh.write("%d\ta%s\t%s\n" % (aid, aset, joined))
        print("written %s" % outfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
