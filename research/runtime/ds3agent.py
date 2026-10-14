"""Privileged helper: performs memory/screenshot operations on request.

Start this ONCE from a shell that can open the game process, then drive it by
writing ipc/req.json (see tools/send_req.ps1). Results land in ipc/res.json.

Requests:
  {"cmd":"info"}
  {"cmd":"probe",  "name":"WEP_ABSORP_POS_PARAM_ST"}
  {"cmd":"rowinfo","param":"WEP_ABSORP_POS_PARAM_ST"}
  {"cmd":"show",   "param":"...", "ids":[1,2], "fields":["leftHang_0"]}
  {"cmd":"stats",  "param":"..."}                      # per-field value histogram
  {"cmd":"copycheck", "param":"..."}                   # are the copies identical?
  {"cmd":"dump",   "param":"EQUIP_PARAM_WEAPON", "raw":64, "ids":[1000000]}
  {"cmd":"set",    "param":"...", "field":"leftHang", "value":-1, "tag":"t1"}
  {"cmd":"restore","tag":"t1"}
  {"cmd":"shot",   "name":"shot-01.png", "crop":[0,0,1740,1440]}
  {"cmd":"keys",   "keys":["f"], "delay":0.5}
  {"cmd":"seq",    "steps":[{...}]}
  {"cmd":"quit"}
"""

import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IPC = os.path.join(ROOT, "ipc")
SAVES = os.path.join(IPC, "saves")
REQ = os.path.join(IPC, "req.json")
RES = os.path.join(IPC, "res.json")
AGENT_LOG = os.path.join(IPC, "agent.log")
sys.path.insert(0, HERE)

os.makedirs(IPC, exist_ok=True)
os.makedirs(SAVES, exist_ok=True)

import ds3mem as M          # noqa: E402
import ds3shot as S         # noqa: E402
import wepabsorp as W       # noqa: E402

TABLE_CACHE = {}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(AGENT_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def tables_for(g, name):
    key = (name.upper(), g.pid, g.base)
    if key not in TABLE_CACHE:
        t0 = time.time()
        tabs = W.open_tables(g, name)
        TABLE_CACHE[key] = tabs
        log(f"located {name}: {len(tabs)} table(s) in {time.time() - t0:.1f}s")
    return TABLE_CACHE[key]


# ---------------------------------------------------------------- commands
def do_info(g, req):
    return {"pid": g.pid, "base": hex(g.base), "size": hex(g.size)}


def do_probe(g, req):
    known = {"param_repo": 0x4798118, "global_hinstance": 0x489D5A0,
             "chr_ins_vmt": 0x284F478, "player_ins_vmt": 0x2857158}
    out = {"base": hex(g.base), "rva": {}}
    for k, rva in known.items():
        v = g.rva_probe(rva)
        out["rva"][k] = {"rva": hex(rva), "value": hex(v) if v is not None else None}
    tabs = tables_for(g, req.get("name", W.PARAM_NAME))
    out["tables"] = [{"table": hex(a), "rows": n} for a, n, _ in tabs]
    return out


def do_params(g, req):
    root, layout, params = g.all_params()
    return {"layout": layout, "count": len(params),
            "params": [{"idx": i, "rows": n, "name": name} for i, cap, t, name, n in params]}


def do_rowinfo(g, req):
    tabs = tables_for(g, req.get("param", W.PARAM_NAME))
    if not tabs:
        return {"error": "not found"}
    t, n, _ = tabs[0]
    sample = []
    for i, (rid, addr) in enumerate(g.rows(t)):
        if i < 4 or i >= n - 2:
            sample.append({"id": rid, "addr": hex(addr), "delta": hex(addr - t)})
    return {"table": hex(t), "rows": n, "name_offset": hex(g.u64(t + 0x10)),
            "length_field": g.u16(t + 0x0A), "sample": sample}


def do_show(g, req):
    name = req.get("param", W.PARAM_NAME)
    tabs = tables_for(g, name)
    if not tabs:
        return {"error": f"{name} not found"}
    ids = req.get("ids")
    fields = req.get("fields") or W.KEY_FIELDS
    data = []
    for rid, addr in W.rows_of(g, tabs[0][0], ids):
        data.append({"id": rid, **{f: W.read_field(g, addr, f) for f in fields}})
    return {"tables": [hex(t) for t, _, _ in tabs], "rows": tabs[0][1],
            "fields": fields, "data": data}


def do_stats(g, req):
    name = req.get("param", W.PARAM_NAME)
    tabs = tables_for(g, name)
    if not tabs:
        return {"error": f"{name} not found"}
    fields = req.get("fields") or list(M.WEP_ABSORP_FIELDS)
    counts = {f: {} for f in fields}
    n = 0
    for _rid, addr in W.rows_of(g, tabs[0][0]):
        n += 1
        for f in fields:
            v = str(W.read_field(g, addr, f))
            counts[f][v] = counts[f].get(v, 0) + 1
    return {"tables": [hex(a) for a, _, _ in tabs], "rows": n, "counts": counts}


def do_copycheck(g, req):
    name = req.get("param", W.PARAM_NAME)
    tabs = tables_for(g, name)
    if len(tabs) < 2:
        return {"copies": len(tabs)}
    n = tabs[0][1]
    size = 0x40 + n * 0x18 + n * 0x60
    ref = g.read(tabs[0][0], size)
    out = []
    for t, _r, _s in tabs:
        blob = g.read(t, size)
        diff = sum(1 for a, b in zip(ref, blob) if a != b)
        out.append({"table": hex(t), "diff_bytes": diff})
    return {"size": size, "copies": out}


def do_dump(g, req):
    needle = req["param"].upper()
    root, layout, params, hits = g.find_param(needle) if not req.get("scan") else (None, None, None, None)
    if hits is None:
        hits = [(0, 0, t, name, n) for t, n, _ in tables_for(g, needle)]
    res = []
    ids = req.get("ids")
    raw = int(req.get("raw", 0))
    for i, cap, t, name, n in hits:
        rows = []
        for rid, addr in g.rows(t):
            if ids and rid not in ids:
                continue
            item = {"id": rid, "addr": hex(addr)}
            if raw:
                item["hex"] = g.read(addr, raw).hex(" ")
            rows.append(item)
            if len(rows) >= 400:
                break
        res.append({"name": name, "table": hex(t), "count": n, "rows": rows})
    return {"hits": res}


def do_set(g, req):
    """Patch WepAbsorpPosParam rows in every table copy (bulk write)."""
    name = req.get("param", W.PARAM_NAME)
    tabs = tables_for(g, name)
    if not tabs:
        return {"error": f"{name} not found"}
    fields = W.GROUPS.get(req["field"], [req["field"]])
    for f in fields:
        if f not in M.WEP_ABSORP_FIELDS:
            raise ValueError(f"unknown field {f}")
    state = {"rows": {}}
    n = 0
    for t, _r, _s in tabs:
        rows = W.rows_of(g, t, req.get("ids"))
        if not rows:
            continue
        start = rows[0][1]
        end = rows[-1][1] + M.WEP_ABSORP_ROW_SIZE
        blob = bytearray(g.read(start, end - start))
        for rid, addr in rows:
            rel = addr - start
            if rel < 0 or rel + M.WEP_ABSORP_ROW_SIZE > len(blob):
                continue
            vals = {}
            for f in fields:
                off, ty = M.WEP_ABSORP_FIELDS[f]
                if ty == "u8":
                    vals[f] = blob[rel + off]
                else:
                    v = blob[rel + off] | (blob[rel + off + 1] << 8)
                    vals[f] = v - 0x10000 if v >= 0x8000 else v
            state["rows"][f"{t:X}:{rid}"] = {"table": t, "id": rid, "vals": vals}
            for f in fields:
                off, ty = M.WEP_ABSORP_FIELDS[f]
                if ty == "u8":
                    blob[rel + off] = req["value"] & 0xFF
                else:
                    blob[rel + off] = req["value"] & 0xFF
                    blob[rel + off + 1] = (req["value"] >> 8) & 0xFF
            n += 1
        g.write(start, bytes(blob))
    tag = req.get("tag")
    if tag:
        with open(os.path.join(SAVES, f"{tag}.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    return {"patched_rows": n, "tables": len(tabs), "fields": fields,
            "value": req["value"], "tag": tag}


def do_peek(g, req):
    addr = int(req["addr"], 16) if isinstance(req["addr"], str) else req["addr"]
    size = int(req.get("size", 128))
    return {"addr": hex(addr), "hex": g.read(addr, size).hex(" ")}


def do_poke(g, req):
    addr = int(req["addr"], 16) if isinstance(req["addr"], str) else req["addr"]
    data = bytes.fromhex(req["hex"].replace(" ", ""))
    return {"addr": hex(addr), "written": g.write(addr, data)}


def do_scan(g, req):
    pat = bytes.fromhex(req["hex"].replace(" ", ""))
    hits = g.scan_bytes([pat], writable_only=req.get("writable", True),
                        max_hits=int(req.get("max", 24)))
    return {"count": len(hits), "hits": [hex(a) for _p, a in hits]}



def do_restore(g, req):
    with open(os.path.join(SAVES, f"{req['tag']}.json"), encoding="utf-8") as fh:
        state = json.load(fh)
    done = 0
    for _key, rec in state["rows"].items():
        for rid, addr in g.rows(rec["table"]):
            if rid == rec["id"]:
                for f, v in rec["vals"].items():
                    W.write_field(g, addr, f, v)
                done += 1
                break
    return {"restored_rows": done, "tag": req["tag"]}


VK = {"f": 0x46, "space": 0x20, "escape": 0x1B, "return": 0x0D, "shift": 0x10,
      "r": 0x52, "e": 0x45, "q": 0x51, "tab": 0x09, "y": 0x59, "g": 0x47,
      "v": 0x56, "ctrl": 0x11, "alt": 0x12, "h": 0x48, "j": 0x4A, "k": 0x4B,
      "z": 0x5A, "x": 0x58, "c": 0x43, "b": 0x42, "n": 0x4E, "m": 0x4D,
      "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "plus": 0x6B,
      "minus": 0x6D, "p": 0x50, "o": 0x4F, "i": 0x49, "u": 0x55, "t": 0x54,
      "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44, "l": 0x4C}
for _d in range(10):
    VK[str(_d)] = 0x30 + _d


_HWND = None


def _game_pid():
    try:
        return M.find_pid()
    except Exception:  # noqa: BLE001
        return None


def _game_hwnd():
    """Cached game window handle, verified to belong to the game process."""
    global _HWND
    import ctypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    pid = _game_pid()
    if _HWND:
        p = ctypes.wintypes.DWORD(0)
        u32.GetWindowThreadProcessId(ctypes.c_void_p(_HWND), ctypes.byref(p))
        if p.value == pid:
            return _HWND
    hwnd = S.find_window("DARK SOULS III")
    if hwnd and pid:
        p = ctypes.wintypes.DWORD(0)
        u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(p))
        if p.value != pid:
            log(f"warning: window 0x{hwnd:X} belongs to pid {p.value}, not {pid}")
    _HWND = hwnd
    return hwnd


def _game_focused():
    import ctypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.GetForegroundWindow.restype = ctypes.c_void_p
    fg = u32.GetForegroundWindow()
    if not fg:
        return False
    p = ctypes.wintypes.DWORD(0)
    u32.GetWindowThreadProcessId(ctypes.c_void_p(fg), ctypes.byref(p))
    return p.value == _game_pid()


def do_focus(g, req):
    import ctypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = _game_hwnd()
    if not hwnd:
        return {"error": "window not found"}
    changed = not _game_focused()
    if changed:
        u32.SetForegroundWindow(hwnd)
    time.sleep(float(req.get("settle", 1.2)))
    return {"changed": changed, "focused_now": _game_focused()}


def do_keys(g, req):
    """Send virtual keys. mode=auto (keybd_event) or post (PostMessage)."""
    import ctypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    KEYUP = 0x0002
    WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
    hwnd = _game_hwnd()
    if not hwnd:
        return {"error": "window not found"}
    mode = req.get("mode", "auto")
    focused_before = _game_focused()
    if mode == "auto" and not focused_before and req.get("focus", True):
        u32.SetForegroundWindow(hwnd)
        time.sleep(float(req.get("focus_settle", 1.0)))

    sent = []
    for k in req["keys"]:
        key = k.lower()
        vk = int(key, 16) if key.startswith("0x") else VK.get(key)
        if vk is None:
            sent.append({"key": k, "error": "unknown"})
            continue
        scan = u32.MapVirtualKeyW(vk, 0)
        hold = float(req.get("hold", 0.15))
        if mode == "post":
            u32.PostMessageW(hwnd, WM_KEYDOWN, vk, 1 | (scan << 16))
            time.sleep(hold)
            u32.PostMessageW(hwnd, WM_KEYUP, vk, 0xC0000000 | (scan << 16) | 1)
        else:
            u32.keybd_event(vk, scan, 0, 0)
            time.sleep(hold)
            u32.keybd_event(vk, scan, KEYUP, 0)
        sent.append({"key": k})
        time.sleep(float(req.get("delay", 0.5)))
    return {"sent": sent, "focused_before": focused_before,
            "focused_after": _game_focused(), "mode": mode}



def _grab_rect(hwnd, crop):
    x, y, cx, cy = S.client_rect_screen(hwnd)
    bgra = S.grab(hwnd, x, y, cx, cy, use_printwindow=False)
    if crop:
        ox, oy, ow, oh = crop
        ow, oh = min(ow, cx - ox), min(oh, cy - oy)
        rows = [bgra[((oy + j) * cx + ox) * 4: ((oy + j) * cx + ox + ow) * 4] for j in range(oh)]
        bgra, cx, cy = b"".join(rows), ow, oh
    return bgra, cx, cy


def _bg_diff(a, b, w, x0, y0, x1, y1):
    cnt = tot = 0
    for y in range(y0, y1):
        o = (y * w + x0) * 4
        for i in range(o, (y * w + x1) * 4, 4):
            d = abs(a[i] - b[i]) + abs(a[i + 1] - b[i + 1]) + abs(a[i + 2] - b[i + 2])
            tot += d
            if d > 18:
                cnt += 1
    n = (x1 - x0) * (y1 - y0)
    return cnt / n, tot / n


def do_shot(g, req):
    name = req.get("name") or f"shot-{int(time.time())}.png"
    path = os.path.join(ROOT, name)
    hwnd = _game_hwnd()
    if not hwnd:
        return {"error": "window not found"}
    crop = req.get("crop")
    guard = req.get("stable_bg")           # [x0,y0,x1,y1] inside the crop
    tol = float(req.get("stable_tol", 0.02))
    tries = int(req.get("stable_tries", 8))
    if guard:
        prev = None
        for i in range(tries):
            cur, cx, cy = _grab_rect(hwnd, crop)
            if prev is not None:
                frac, mean = _bg_diff(prev, cur, cx, *guard)
                if frac < tol / 100.0 or frac * 100 < tol:
                    S.write_png(path, cx, cy, cur)
                    return {"file": name, "size": [cx, cy], "stable": True,
                            "tries": i + 1, "bg_frac": round(frac * 100, 3)}
            prev = cur
            time.sleep(0.35)
        S.write_png(path, cx, cy, cur)
        return {"file": name, "size": [cx, cy], "stable": False, "tries": tries}
    bgra, cx, cy = _grab_rect(hwnd, crop)
    S.write_png(path, cx, cy, bgra)
    return {"file": name, "size": [cx, cy]}



def do_mouse(g, req):
    """Inject relative mouse motion (camera control). dx>0 looks right."""
    import ctypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = _game_hwnd()
    if not hwnd:
        return {"error": "window not found"}
    if req.get("focus", True):
        u32.SetForegroundWindow(hwnd)
        time.sleep(float(req.get("focus_settle", 0.6)))
    dx, dy = int(req.get("dx", 0)), int(req.get("dy", 0))
    steps = max(1, int(req.get("steps", 24)))
    per_x, per_y = dx / steps, dy / steps
    acc_x = acc_y = 0.0
    for _ in range(steps):
        acc_x += per_x
        acc_y += per_y
        sx, sy = int(round(acc_x)), int(round(acc_y))
        acc_x -= sx
        acc_y -= sy
        u32.mouse_event(0x0001, sx, sy, 0, 0)
        time.sleep(0.012)
    time.sleep(float(req.get("settle", 0.4)))
    return {"dx": dx, "dy": dy, "steps": steps}


HANDLERS = {"info": do_info, "probe": do_probe, "params": do_params,
            "rowinfo": do_rowinfo, "show": do_show, "stats": do_stats,
            "copycheck": do_copycheck, "dump": do_dump, "set": do_set,
            "restore": do_restore, "keys": do_keys, "peek": do_peek,
            "poke": do_poke, "scan": do_scan, "focus": do_focus,
            "mouse": do_mouse}


def execute(req):
    cmd = req.get("cmd")
    if cmd == "quit":
        return {"quit": True}
    if cmd == "seq":
        out = []
        for step in req["steps"]:
            try:
                out.append(execute(step))
            except BaseException as exc:  # noqa: BLE001
                out.append({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc()[-600:]})
        return {"steps": out}
    if cmd == "shot":
        return do_shot(None, req)
    h = HANDLERS.get(cmd)
    if h is None:
        return {"error": f"unknown cmd {cmd}"}
    return h(M.Game(), req)


def main():
    log(f"agent up: pid={os.getpid()} ipc={IPC}")
    while True:
        if os.path.exists(REQ):
            raw = None
            for _ in range(60):
                try:
                    with open(REQ, encoding="utf-8-sig") as fh:
                        raw = json.load(fh)
                    break
                except (OSError, json.JSONDecodeError):
                    time.sleep(0.2)
            if raw is None:
                log("could not parse req.json; dropping")
                try:
                    os.remove(REQ)
                except OSError:
                    pass
                continue
            try:
                os.remove(REQ)
            except OSError:
                pass
            started = time.time()
            try:
                res = execute(raw)
                res["ok"] = True
            except BaseException as exc:  # noqa: BLE001
                res = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                       "trace": traceback.format_exc()[-1200:]}
            res["seconds"] = round(time.time() - started, 2)
            log(f"{raw.get('cmd')} -> {'ok' if res.get('ok') else res.get('error')}"
                f" ({res['seconds']}s)")
            if res.get("quit"):
                with open(RES, "w", encoding="utf-8") as fh:
                    json.dump({"ok": True, "bye": True}, fh, indent=1)
                return
            tmp = RES + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1)
            os.replace(tmp, RES)
        time.sleep(0.25)


if __name__ == "__main__":
    main()
