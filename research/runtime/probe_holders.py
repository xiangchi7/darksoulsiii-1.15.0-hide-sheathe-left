"""Report which structures hold each in-memory WEP_ABSORP_POS_PARAM_ST table.

Why: the param patch is global by nature.  If DS3 keeps a separate PC and NPC
copy of this table (the fromsoftware-rs layout says a SoloParamCell can hold up
to 8 params, and several params exist twice -- e.g. ATK_PARAM_ST for NPCs at
index N and for PCs at N+1), then patching only the player's copy gives
"player only, NPCs untouched".  This script finds out whether that is the case:
it walks  table -> FD4ParamResCap -> ParamResCap -> SoloParamCell  and prints
every cell (with its len and the params inside) that holds such a table.

RUN IT OUTSIDE THE DSH SANDBOX, with the game running:

    python probe_holders.py

Takes ~1.5 minutes (three full memory scans of the game process).
"""

import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3mem as M  # noqa: E402

PARAM = "WEP_ABSORP_POS_PARAM_ST"
RESCAP_PARAM_OFF = 0x68   # ParamResCap.param   -> FD4ParamResCap
FD4_TABLE_OFF    = 0x68   # FD4ParamResCap.table -> ParamTable
FD4_SIZE_OFF     = 0x60   # FD4ParamResCap.table_size
TABLE_LEN_OFF    = 0x0A
TABLE_NAME_OFF   = 0x10


def table_name(g, table):
    if not table or not g.looks_like_heap(table):
        return None
    try:
        off = g.u64(table + TABLE_NAME_OFF)
        if off > 0x2000:
            return None
        return g.cstr(table + off, 64) or None
    except OSError:
        return None


def main():
    g = M.Game()
    print(f"pid={g.pid}  base=0x{g.base:X}\n")

    t0 = time.time()
    tables = [t for t, n, s in g.find_param_table(PARAM)]
    print(f"[1/3] tables named {PARAM}: {len(tables)}   ({time.time()-t0:.1f}s)")
    for i, t in enumerate(tables):
        n = g.u16(t + TABLE_LEN_OFF)
        print(f"        #{i} table=0x{t:X} rows={n}")
    if not tables:
        print("no tables found - is the game in a loaded save?")
        return 1

    # ---- who points at each table (FD4ParamResCap.table) -------------------
    t0 = time.time()
    n1 = {struct.pack("<Q", t): t for t in tables}
    hits1 = g.scan_bytes(list(n1.keys()), max_hits=512)
    fd4 = {}
    for nd, addr in hits1:
        t = n1[nd]
        cand = addr - FD4_TABLE_OFF
        try:
            name = g.cstr(cand + 0x08, 64)
            size = g.u64(cand + FD4_SIZE_OFF)
        except OSError:
            continue
        fd4.setdefault(t, []).append((cand, addr, name, size))
    print(f"\n[2/3] FD4ParamResCap holders found   ({time.time()-t0:.1f}s)")
    for t in tables:
        print(f"  table 0x{t:X}")
        for cand, addr, name, size in fd4.get(t, []):
            print(f"        FD4=0x{cand:X} (ptr@0x{addr:X}) name={name!r} table_size=0x{size:X}")

    # ---- who points at each FD4ParamResCap (ParamResCap.param) -------------
    t0 = time.time()
    fd4addrs = sorted({c for v in fd4.values() for (c, _, _, _) in v})
    n2 = {struct.pack("<Q", c): c for c in fd4addrs}
    hits2 = g.scan_bytes(list(n2.keys()), max_hits=512)
    rescaps = {}
    for nd, addr in hits2:
        resc = addr - RESCAP_PARAM_OFF
        try:
            vt = g.u64(resc)
        except OSError:
            continue
        rescaps.setdefault(n2[nd], []).append((resc, addr, vt))
    print(f"\n[3/3] ParamResCap holders found   ({time.time()-t0:.1f}s)")
    for fd in fd4addrs:
        for resc, addr, vt in rescaps.get(fd, []):
            ok = g.base <= vt < g.base + g.size
            print(f"  FD4=0x{fd:X} -> ParamResCap=0x{resc:X} (ptr@0x{addr:X}) "
                  f"vftable=0x{vt:X} {'ok' if ok else 'SUSPECT'}")

    # ---- who points at each ParamResCap (SoloParamCell.params[j]) ----------
    t0 = time.time()
    resaddrs = sorted({r for v in rescaps.values() for (r, _, _) in v})
    n3 = {struct.pack("<Q", r): r for r in resaddrs}
    hits3 = g.scan_bytes(list(n3.keys()), max_hits=1024)
    print(f"\n[4/4] SoloParamCell slots found   ({time.time()-t0:.1f}s)")
    seen_cells = []
    for nd, addr in hits3:
        resc = n3[nd]
        found = False
        for j in range(8):
            cell = addr - 0x08 - j * 8
            if cell in [c for c, _ in seen_cells]:
                found = True
                break
            try:
                ln = g.u64(cell)
            except OSError:
                continue
            if not (0 < ln <= 8):
                continue
            members = []
            for k in range(ln):
                try:
                    p = g.u64(cell + 0x08 + k * 8)
                    fd4p = g.u64(p + RESCAP_PARAM_OFF)
                    tb = g.u64(fd4p + FD4_TABLE_OFF) if fd4p else 0
                except OSError:
                    members.append(("?", "?", "?"))
                    continue
                members.append((hex(p), hex(tb), table_name(g, tb)))
            seen_cells.append((cell, len(members)))
            mark = "  <== MULTI-PARAM CELL" if len(members) > 1 else ""
            print(f"  cell=0x{cell:X} len={len(members)}{mark}")
            for p, tb, nm in members:
                print(f"        ParamResCap={p} table={tb} name={nm!r}")
            found = True
            break
        if not found:
            print(f"  (ptr 0x{addr:X} -> ParamResCap 0x{resc:X} did not resolve to a cell)")

    print("\n=== summary ===")
    print(f"tables: {len(tables)}  distinct ParamResCap: {len(resaddrs)}  "
          f"distinct cells: {len(seen_cells)}")
    multi = [c for c, n in seen_cells if n > 1]
    if multi:
        print("MULTI-PARAM CELLS FOUND -> a PC/NPC split is plausible:")
        for c in multi:
            print(f"   cell 0x{c:X}")
    else:
        print("no cell holds more than one param -> the copies are very likely "
              "the same logical table held by several owners (no PC/NPC split "
              "reachable this way).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
