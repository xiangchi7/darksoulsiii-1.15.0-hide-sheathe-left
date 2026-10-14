#!/usr/bin/env python3
"""Dump the full animation-id -> state-names map from a DS3 behaviour bundle.

usage: py animmap.py <cXXXX.behbnd.dcx> <out.tsv>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3bnd as B  # noqa: E402
import behmap as M  # noqa: E402


def main():
    path, out = sys.argv[1], sys.argv[2]
    data = B.load(path)
    entries = M.build_map(data)
    with open(out, "w", encoding="utf-8", errors="replace") as fh:
        fh.write("animId\tset\tnames\n")
        for aid, aset, marker, names, off in entries:
            joined = " ".join(n for n, _ in names)
            fh.write("%d\t%s\t%s\n" % (aid, aset, joined))
    print("%s: %d animation markers -> %s" % (os.path.basename(path), len(entries), out))


if __name__ == "__main__":
    main()
