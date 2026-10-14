"""Experiment driver for WepAbsorpPosParam (the weapon attach / hide param).

Row size 0x60; field offsets come from the DS3 paramdef
(WEP_ABSORP_POS_PARAM_ST, 91 rows).  Field groups:
  leftHang      -> leftHang_0..3        attach poly for a sheathed LEFT-hand weapon
  rightHang     -> rightHang_0..3
  invisible     -> wepInvisibleType_0..3
  dispLeftHang  -> dispPosType_leftHang_0..3
  dispRightHang -> dispPosType_rightHang_0..3
  leftBoth      -> leftBoth_0..3
  skelBind      -> isSkeletonBind
  hangPosType   -> hangPosType
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3mem as M  # noqa: E402

GROUPS = {
    "leftHang": [f"leftHang_{i}" for i in range(4)],
    "rightHang": [f"rightHang_{i}" for i in range(4)],
    "left": [f"left_{i}" for i in range(4)],
    "right": [f"right_{i}" for i in range(4)],
    "both": [f"both_{i}" for i in range(4)],
    "invisible": [f"wepInvisibleType_{i}" for i in range(4)],
    "dispLeftHang": [f"dispPosType_leftHang_{i}" for i in range(4)],
    "dispRightHang": [f"dispPosType_rightHang_{i}" for i in range(4)],
    "leftBoth": [f"leftBoth_{i}" for i in range(4)],
    "rightModel1": ["right_1"],
    "rightOffhand": ["right_1", "right_2", "right_3"],
    "leftModel1": ["left_1"],
    "skelBind": ["isSkeletonBind"],
    "hangPosType": ["hangPosType"],
}

PARAM_NAME = "WEP_ABSORP_POS_PARAM_ST"

# compact fields for reporting
KEY_FIELDS = ["hangPosType", "isSkeletonBind",
              "left_0", "left_1", "left_2", "left_3",
              "both_0", "both_1", "both_2", "both_3",
              "leftHang_0", "leftHang_1", "leftHang_2", "leftHang_3",
              "rightHang_0", "rightHang_1", "rightHang_2", "rightHang_3",
              "wepInvisibleType_0", "wepInvisibleType_1",
              "wepInvisibleType_2", "wepInvisibleType_3",
              "dispPosType_leftHang_0", "dispPosType_leftHang_1",
              "dispPosType_leftHang_2", "dispPosType_leftHang_3"]


def open_tables(g, name=PARAM_NAME):
    """All in-memory copies of the table (the game keeps several)."""
    tabs = g.find_param_table(name)
    if not tabs:
        t, n, _how = g.param_table_by_name(name)
        if t:
            tabs = [(t, n, 0)]
    return tabs


def rows_of(g, table, ids=None):
    out = []
    for rid, addr in g.rows(table):
        if ids and rid not in ids:
            continue
        out.append((rid, addr))
    return out


def read_field(g, addr, field):
    off, ty = M.WEP_ABSORP_FIELDS[field]
    return g.u8(addr + off) if ty == "u8" else g.s16(addr + off)


def write_field(g, addr, field, value):
    off, ty = M.WEP_ABSORP_FIELDS[field]
    if ty == "u8":
        g.write_u8(addr + off, value)
    else:
        g.write_u16(addr + off, value & 0xFFFF)


def fmt_row(rid, vals):
    return (f"id={rid:<6} skel={vals['isSkeletonBind']} hang={vals['hangPosType']} "
            f"left={vals['left_0']},{vals['left_1']},{vals['left_2']},{vals['left_3']} "
            f"both={vals['both_0']},{vals['both_1']},{vals['both_2']},{vals['both_3']} "
            f"LHang={vals['leftHang_0']},{vals['leftHang_1']},"
            f"{vals['leftHang_2']},{vals['leftHang_3']} "
            f"RHang={vals['rightHang_0']},{vals['rightHang_1']},"
            f"{vals['rightHang_2']},{vals['rightHang_3']} "
            f"inv={vals['wepInvisibleType_0']},{vals['wepInvisibleType_1']},"
            f"{vals['wepInvisibleType_2']},{vals['wepInvisibleType_3']} "
            f"dLH={vals['dispPosType_leftHang_0']},{vals['dispPosType_leftHang_1']},"
            f"{vals['dispPosType_leftHang_2']},{vals['dispPosType_leftHang_3']}")


# ------------------------------------------------------------------ CLI
def cmd_show(g, a):
    tabs = open_tables(g)
    if not tabs:
        raise RuntimeError("param not found")
    print(f"{PARAM_NAME}: {len(tabs)} copies {[hex(t) for t, _, _ in tabs]}")
    t = tabs[0][0]
    for rid, addr in rows_of(g, t, a.ids):
        print("  " + fmt_row(rid, {f: read_field(g, addr, f) for f in KEY_FIELDS}))


def cmd_set(g, a):
    tabs = open_tables(g)
    fields = GROUPS.get(a.field, [a.field])
    for f in fields:
        if f not in M.WEP_ABSORP_FIELDS:
            raise ValueError(f"unknown field {f}; groups: {list(GROUPS)}")
    state = {"rows": {}}
    n = 0
    for t, _rows, _ in tabs:
        for rid, addr in rows_of(g, t, a.ids):
            key = f"{t:X}:{rid}"
            state["rows"][key] = {"table": t, "id": rid,
                                  "vals": {f: read_field(g, addr, f) for f in fields}}
            for f in fields:
                write_field(g, addr, f, a.value)
            n += 1
    print(f"patched {n} rows in {len(tabs)} copies: {fields} <- {a.value}")
    if a.save:
        with open(a.save, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        print(f"saved originals to {a.save}")


def cmd_restore(g, a):
    with open(a.state, encoding="utf-8") as fh:
        state = json.load(fh)
    done = 0
    for key, rec in state["rows"].items():
        t = rec["table"]
        for rid, addr in g.rows(t):
            if rid == rec["id"]:
                for f, v in rec["vals"].items():
                    write_field(g, addr, f, v)
                done += 1
                break
    print(f"restored {done} rows")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--ids", type=int, nargs="*", default=None)
    p = sub.add_parser("set")
    p.add_argument("field")
    p.add_argument("value", type=int)
    p.add_argument("--ids", type=int, nargs="*", default=None)
    p.add_argument("--save", default=None)
    r = sub.add_parser("restore")
    r.add_argument("state")
    args = ap.parse_args()
    g = M.Game()
    print(f"[pid={g.pid} base=0x{g.base:X}]")
    {"show": cmd_show, "set": cmd_set, "restore": cmd_restore}[args.cmd](g, args)


if __name__ == "__main__":
    main()
