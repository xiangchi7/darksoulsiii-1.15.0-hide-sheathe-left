#!/usr/bin/env python3
"""Read-only dump of every WepAbsorpPosParam row from a live DarkSoulsIII.exe.

usage: py dumpwep.py [out.json]
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds3mem as M  # noqa: E402

PARAM = "WEP_ABSORP_POS_PARAM_ST"


def newest_pid():
    """pid of the DarkSoulsIII process that owns the game window.

    Dark Souls III starts a short-lived launcher process and then the real game;
    reading the launcher (which never reaches the param scan) returns vanilla data.
    """
    import ctypes
    from ctypes import wintypes as w

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    proto = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    found = []

    def cb(hwnd, _lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "DARK SOULS III" in buf.value:
                pid = w.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    found.append(pid.value)
        return True

    user32.EnumWindows(proto(cb), 0)
    if found:
        return found[0]
    return M.find_pid() if hasattr(M, "find_pid") else None

SHOW = ["left_0", "left_1", "left_2", "left_3",
        "both_0", "leftHang_0", "leftHang_1", "leftHang_2", "leftHang_3",
        "right_0", "right_1", "right_2", "right_3", "rightHang_0",
        "leftBoth_0", "wepInvisibleType_0", "hangPosType"]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else None
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if pid is None:
        pid = newest_pid()
    g = M.Game(pid=pid) if pid else M.Game()
    print("[pid=%d base=0x%X]" % (g.pid, g.base))

    tabs = g.find_param_table(PARAM)
    if not tabs:
        t, n, _how = g.param_table_by_name(PARAM)
        if t:
            tabs = [(t, n, 0)]
    if not tabs:
        print("param table not found")
        return 1
    print("table copies: %s" % [hex(t) for t, _, _ in tabs])

    rows = {}
    for ti, (t, _n, _how) in enumerate(tabs):
        pairs = list(g.rows(t))
        print("  copy %d @0x%X: %d rows" % (ti, t, len(pairs)))
        for rid, addr in pairs:
            vals = {}
            for f, (off, ty) in M.WEP_ABSORP_FIELDS.items():
                vals[f] = g.u8(addr + off) if ty == "u8" else g.s16(addr + off)
            rows.setdefault(rid, {})["copy%d" % ti] = {"addr": "0x%X" % addr, "vals": vals}

    print("rows: %d" % len(rows))
    for rid in sorted(rows):
        vals = rows[rid]["copy0"]["vals"]
        print("id=%-5d %s" % (rid, " ".join("%s=%d" % (k, vals[k]) for k in SHOW)))

    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
        print("saved %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
