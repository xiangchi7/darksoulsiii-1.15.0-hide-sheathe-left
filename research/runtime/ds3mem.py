"""DS3 1.15.x runtime memory toolkit.

Resolves the game's param repository, can list param tables, dump rows and
patch single fields. Layouts come from fromsoftware-rs (darksouls3 crate):

  SoloParamRepository (singleton, base + PARAM_REPO_RVA -> pointer)
    +0x68  params[0x61] : SoloParamCell   (0x48 bytes each)
           +0x00 len (u64)
           +0x08 params[0] (ParamResCap*)
  ParamResCap
    +0x68  param : FD4ParamResCap*
  FD4ParamResCap
    +0x60 table_size (u64)
    +0x68 table : ParamTable*
  ParamTable
    +0x0A length (u16)
    +0x10 name_offset (u64)  -> snake case name (C string)
    +0x40 row_info[length]   (ParamRowInfo = 0x18: id u64, offset u64, unk u64)
    row data at ParamTable + offset

  CSRegulationManager (alternative route)
    +0x10 params : DLVector<ParamResCap*>  (ptr, size, capacity)
"""

import argparse
import ctypes
import struct
import sys
import time
from ctypes import wintypes as w

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

k32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k32.OpenProcess.restype = w.HANDLE
k32.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = w.BOOL
k32.WriteProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.restype = w.BOOL
k32.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
k32.CreateToolhelp32Snapshot.restype = w.HANDLE

PROCESS_ALL_ACCESS = 0x1F0FFF
TH32CS_SNAPPROCESS = 0x2
TH32CS_SNAPMODULE = 0x8
TH32CS_SNAPMODULE32 = 0x10
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260

# me3 (old DS3 support): PARAM_REPOSITORY = "DarkSoulsIII.exe"#0x4798118
PARAM_REPO_RVA = 0x4798118

REPO_PARAMS_OFF = 0x68
CELL_SIZE = 0x48
REPO_PARAM_COUNT = 0x61
RESCAP_PARAM_OFF = 0x68
FD4_TABLE_OFF = 0x68
TABLE_LEN_OFF = 0x0A
TABLE_NAME_OFF = 0x10
TABLE_ROWINFO_OFF = 0x40
ROWINFO_SIZE = 0x18


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", w.DWORD),
        ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD),
        ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
        ("szExeFile", ctypes.c_char * MAX_PATH),
    ]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", w.DWORD), ("th32ModuleID", w.DWORD), ("th32ProcessID", w.DWORD),
        ("GlblcntUsage", w.DWORD), ("ProccntUsage", w.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("modBaseSize", w.DWORD),
        ("hModule", w.HMODULE), ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * MAX_PATH),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", w.DWORD), ("RegionSize", ctypes.c_size_t),
        ("State", w.DWORD), ("Protect", w.DWORD), ("Type", w.DWORD),
    ]


k32.VirtualQueryEx.argtypes = [w.HANDLE, ctypes.c_void_p,
                               ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
READABLE = (0x02, 0x04, 0x08, 0x20, 0x40, 0x80)
WRITABLE = (0x04, 0x08, 0x40, 0x80)


def find_pid(name="DarkSoulsIII.exe"):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        raise OSError("CreateToolhelp32Snapshot failed")
    try:
        e = PROCESSENTRY32()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32First(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.decode("mbcs", "replace").lower() == name.lower():
                return e.th32ProcessID
            ok = k32.Process32Next(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return None


class Game:
    def __init__(self, pid=None):
        self.pid = pid or find_pid()
        if not self.pid:
            raise RuntimeError("DarkSoulsIII.exe is not running")
        self.h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, self.pid)
        if not self.h:
            raise RuntimeError(f"OpenProcess failed: {ctypes.get_last_error()}")
        self.base, self.size = self._module("DarkSoulsIII.exe")

    # ---------- raw access ----------
    def _module(self, name):
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self.pid)
        if snap == INVALID_HANDLE_VALUE:
            raise OSError("module snapshot failed")
        try:
            me = MODULEENTRY32()
            me.dwSize = ctypes.sizeof(me)
            ok = k32.Module32First(snap, ctypes.byref(me))
            while ok:
                if me.szModule.decode("mbcs", "replace").lower() == name.lower():
                    return ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value, me.modBaseSize
                ok = k32.Module32Next(snap, ctypes.byref(me))
        finally:
            k32.CloseHandle(snap)
        raise RuntimeError(f"module {name} not found")

    def read(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
            raise OSError(f"ReadProcessMemory 0x{addr:X} ({size}) failed: {ctypes.get_last_error()}")
        return buf.raw[: got.value]

    def try_read(self, addr, size):
        try:
            return self.read(addr, size)
        except OSError:
            return None

    def write(self, addr, data):
        wrote = ctypes.c_size_t(0)
        if not k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(wrote)):
            raise OSError(f"WriteProcessMemory 0x{addr:X} failed: {ctypes.get_last_error()}")
        return wrote.value

    # ---------- typed helpers ----------
    def u8(self, a):
        return self.read(a, 1)[0]

    def u16(self, a):
        return struct.unpack("<H", self.read(a, 2))[0]

    def s16(self, a):
        return struct.unpack("<h", self.read(a, 2))[0]

    def u32(self, a):
        return struct.unpack("<I", self.read(a, 4))[0]

    def u64(self, a):
        return struct.unpack("<Q", self.read(a, 8))[0]

    def s64(self, a):
        return struct.unpack("<q", self.read(a, 8))[0]

    def write_u16(self, a, v):
        return self.write(a, struct.pack("<H", v & 0xFFFF))

    def write_u8(self, a, v):
        return self.write(a, struct.pack("<B", v & 0xFF))

    def cstr(self, a, maxlen=64):
        b = self.try_read(a, maxlen) or b""
        z = b.find(b"\x00")
        return b[: z if z >= 0 else len(b)].decode("utf-8", "replace")

    # ---------- validation ----------
    def looks_like_vftable(self, ptr):
        return ptr is not None and self.base <= ptr < self.base + self.size

    def looks_like_heap(self, ptr):
        return ptr is not None and 0x10000 <= ptr < 0x7FFF_FFFF_FFFF

    # ---------- memory scanning ----------
    def regions(self, writable_only=True):
        """Yield (base, size) for committed readable regions."""
        addr = 0
        mbi = MEMORY_BASIC_INFORMATION()
        while addr < 0x7FFF_FFFF_0000:
            got = k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr),
                                     ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not got:
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize or 0
            prot = mbi.Protect & 0xFF
            if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD)
                    and prot in READABLE
                    and (not writable_only or prot in WRITABLE)):
                yield base, size
            if size == 0:
                break
            addr = base + size

    def scan_bytes(self, needles, writable_only=True, chunk=8 << 20, max_hits=64):
        """Find raw byte patterns in committed memory. Returns [(needle, addr)]."""
        hits = []
        for base, size in self.regions(writable_only):
            off = 0
            while off < size:
                n = min(chunk, size - off)
                blob = self.try_read(base + off, n)
                if blob:
                    for nd in needles:
                        p = blob.find(nd)
                        while p >= 0:
                            hits.append((nd, base + off + p))
                            if len(hits) >= max_hits:
                                return hits
                            p = blob.find(nd, p + 1)
                off += n
        return hits

    def find_param_table(self, name, back=0x200000):
        """Locate a ParamTable by its snake-case name string.

        The table stores `name_offset` (u64 at table+0x10) relative to itself,
        so the byte just before the string must be `table + name_offset`.
        """
        want = name.encode()
        out = []
        for _, saddr in self.scan_bytes([want]):
            start = max(0, saddr - back)
            blob = self.try_read(start, saddr - start + 8)
            if not blob:
                continue
            span = len(blob) - 8
            for delta in range(0x40, span):
                tb = saddr - delta
                if struct.unpack_from("<Q", blob, span - delta + TABLE_NAME_OFF)[0] != delta:
                    continue
                ln = struct.unpack_from("<H", blob, span - delta + TABLE_LEN_OFF)[0]
                if 0 < ln < 40000:
                    out.append((tb, ln, saddr))
                    break
        return out

    def param_table_by_name(self, name):
        """Return (table, rows, how) for a param, via repository or name scan."""
        try:
            root, layout, params = self.all_params()
            for i, cap, t, nm, n in params:
                if nm.upper() == name.upper():
                    return t, n, "repo"
        except Exception:  # noqa: BLE001
            pass
        tabs = self.find_param_table(name)
        if tabs:
            return tabs[0][0], tabs[0][1], "scan"
        return None, None, "not-found"

    def rva_probe(self, rva):
        raw = self.try_read(self.base + rva, 8)
        if not raw:
            return None
        return struct.unpack("<Q", raw)[0]

    # ---------- param repository ----------
    def resolve(self):
        """Return (repo_addr, layout_name, cells) where cells = [(index, ParamResCap*)]."""
        cand = self.try_read(self.base + PARAM_REPO_RVA, 8)
        if not cand:
            raise RuntimeError("cannot read PARAM_REPO_RVA")
        root = struct.unpack("<Q", cand)[0]
        self.repo_ptr_addr = self.base + PARAM_REPO_RVA
        self.repo_root = root
        if not self.looks_like_heap(root):
            raise RuntimeError(f"PARAM_REPO_RVA points at 0x{root:X} (not plausible)")

        # Route A: root is SoloParamRepository
        cells = []
        for i in range(REPO_PARAM_COUNT):
            cell = root + REPO_PARAMS_OFF + i * CELL_SIZE
            ln = self.try_read(cell, 8)
            if not ln:
                break
            ln = struct.unpack("<Q", ln)[0]
            if ln == 0:
                continue
            p = self.try_read(cell + 8, 8)
            if not p:
                continue
            p = struct.unpack("<Q", p)[0]
            if self.looks_like_heap(p):
                cells.append((i, p))
        if len(cells) >= 20:
            return root, "SoloParamRepository", cells

        # Route B: root is CSRegulationManager -> DLVector<ParamResCap*>
        v = self.try_read(root + 0x10, 0x18)
        if v:
            ptr, a, b = struct.unpack("<QQQ", v)
            n = a if 0 < a < 1000 else b
            if self.looks_like_heap(ptr) and 0 < n < 1000:
                cells = []
                for i in range(n):
                    p = self.try_read(ptr + i * 8, 8)
                    if not p:
                        break
                    p = struct.unpack("<Q", p)[0]
                    if self.looks_like_heap(p):
                        cells.append((i, p))
                if len(cells) >= 20:
                    return root, "CSRegulationManager", cells
        raise RuntimeError("could not recognise the param repository layout")

    def param_table(self, rescap):
        fd4 = self.u64(rescap + RESCAP_PARAM_OFF)
        if not self.looks_like_heap(fd4):
            return None
        table = self.u64(fd4 + FD4_TABLE_OFF)
        if not self.looks_like_heap(table):
            return None
        return table

    def param_name(self, table):
        off = self.u64(table + TABLE_NAME_OFF)
        if off > 0x2000:
            return None
        name = self.cstr(table + off, 96)
        return name or None

    def param_length(self, table):
        return self.u16(table + TABLE_LEN_OFF)

    def rows(self, table):
        """Yield (row_id, row_addr)."""
        n = self.param_length(table)
        blob = self.try_read(table + TABLE_ROWINFO_OFF, n * ROWINFO_SIZE)
        if not blob:
            return
        for i in range(n):
            rid, off, _ = struct.unpack_from("<QQQ", blob, i * ROWINFO_SIZE)
            yield rid, table + off

    def all_params(self):
        root, layout, cells = self.resolve()
        out = []
        for i, cap in cells:
            t = self.param_table(cap)
            if t is None:
                continue
            name = self.param_name(t)
            if not name:
                continue
            name = name[:64]
            if not all(32 <= ord(c) < 127 for c in name):
                continue
            out.append((i, cap, t, name, self.param_length(t)))
        return root, layout, out

    def find_param(self, needle):
        root, layout, params = self.all_params()
        needle = needle.upper()
        hits = [p for p in params if needle in p[3].upper()]
        return root, layout, params, hits


# ----------------------------------------------------------------------------
# WepAbsorpPosParam row layout (from the DS3 paramdef, row size 0x60)
# ----------------------------------------------------------------------------
WEP_ABSORP_FIELDS = {
    "hangPosType": (0x00, "u8"),
    "isSkeletonBind": (0x01, "u8"),
    "right_0": (0x04, "s16"), "left_0": (0x06, "s16"), "both_0": (0x08, "s16"),
    "leftHang_0": (0x0A, "s16"), "rightHang_0": (0x0C, "s16"),
    "right_1": (0x0E, "s16"), "left_1": (0x10, "s16"), "both_1": (0x12, "s16"),
    "leftHang_1": (0x14, "s16"), "rightHang_1": (0x16, "s16"),
    "right_2": (0x18, "s16"), "left_2": (0x1A, "s16"), "both_2": (0x1C, "s16"),
    "leftHang_2": (0x1E, "s16"), "rightHang_2": (0x20, "s16"),
    "right_3": (0x22, "s16"), "left_3": (0x24, "s16"), "both_3": (0x26, "s16"),
    "leftHang_3": (0x28, "s16"), "rightHang_3": (0x2A, "s16"),
    "wepInvisibleType_0": (0x2C, "u8"), "wepInvisibleType_1": (0x2D, "u8"),
    "wepInvisibleType_2": (0x2E, "u8"), "wepInvisibleType_3": (0x2F, "u8"),
    "leftBoth_0": (0x30, "s16"), "leftBoth_1": (0x32, "s16"),
    "leftBoth_2": (0x34, "s16"), "leftBoth_3": (0x36, "s16"),
    "dispPosType_right_0": (0x38, "u8"), "dispPosType_left_0": (0x39, "u8"),
    "dispPosType_rightBoth_0": (0x3A, "u8"), "dispPosType_leftBoth_0": (0x3B, "u8"),
    "dispPosType_rightHang_0": (0x3C, "u8"), "dispPosType_leftHang_0": (0x3D, "u8"),
    "dispPosType_right_1": (0x3E, "u8"), "dispPosType_left_1": (0x3F, "u8"),
    "dispPosType_rightBoth_1": (0x40, "u8"), "dispPosType_leftBoth_1": (0x41, "u8"),
    "dispPosType_rightHang_1": (0x42, "u8"), "dispPosType_leftHang_1": (0x43, "u8"),
    "dispPosType_right_2": (0x44, "u8"), "dispPosType_left_2": (0x45, "u8"),
    "dispPosType_rightBoth_2": (0x46, "u8"), "dispPosType_leftBoth_2": (0x47, "u8"),
    "dispPosType_rightHang_2": (0x48, "u8"), "dispPosType_leftHang_2": (0x49, "u8"),
    "dispPosType_right_3": (0x4A, "u8"), "dispPosType_left_3": (0x4B, "u8"),
    "dispPosType_rightBoth_3": (0x4C, "u8"), "dispPosType_leftBoth_3": (0x4D, "u8"),
    "dispPosType_rightHang_3": (0x4E, "u8"), "dispPosType_leftHang_3": (0x4F, "u8"),
}
WEP_ABSORP_ROW_SIZE = 0x60


def _fmt_row(g, addr):
    vals = {}
    for name, (off, ty) in WEP_ABSORP_FIELDS.items():
        vals[name] = g.u8(addr + off) if ty == "u8" else g.s16(addr + off)
    return vals


def _absorp_line(rid, v):
    return (
        f"id={rid:<6} hangPosType={v['hangPosType']:<3} skelBind={v['isSkeletonBind']:<2} "
        f"L{ v['left_0']},{v['left_1']},{v['left_2']},{v['left_3']} "
        f"LH{ v['leftHang_0']},{v['leftHang_1']},{v['leftHang_2']},{v['leftHang_3']} "
        f"RH{ v['rightHang_0']},{v['rightHang_1']},{v['rightHang_2']},{v['rightHang_3']} "
        f"inv={v['wepInvisibleType_0']},{v['wepInvisibleType_1']},"
        f"{v['wepInvisibleType_2']},{v['wepInvisibleType_3']} "
        f"dspLH={v['dispPosType_leftHang_0']},{v['dispPosType_leftHang_1']},"
        f"{v['dispPosType_leftHang_2']},{v['dispPosType_leftHang_3']}"
    )


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def cmd_info(g, a):
    print(f"pid       = {g.pid}")
    print(f"base      = 0x{g.base:X}  size=0x{g.size:X}")
    root, layout, cells = g.resolve()
    print(f"root      = 0x{root:X}  (via 0x{g.repo_ptr_addr:X}, rva 0x{PARAM_REPO_RVA:X})")
    print(f"layout    = {layout}  cells={len(cells)}")


def cmd_params(g, a):
    root, layout, params = g.all_params()
    print(f"# root=0x{root:X} layout={layout} params={len(params)}")
    for i, cap, t, name, n in params:
        print(f"  [{i:>3}] rows={n:<6} table=0x{t:X}  {name}")


def cmd_dump(g, a):
    root, layout, params, hits = g.find_param(a.needle)
    if not hits:
        print("no param matched")
        return
    for i, cap, t, name, n in hits:
        print(f"== [{i}] {name}  rows={n} table=0x{t:X}")
        if a.raw:
            print(f"   rowinfo@0x{t + TABLE_ROWINFO_OFF:X}  name@{t + g.u64(t + TABLE_NAME_OFF):X}")
        for rid, addr in g.rows(t):
            if a.raw:
                blob = g.read(addr, min(a.raw, 0x120))
                print(f"  id={rid:<6} @0x{addr:X} " + blob.hex(" "))
            if name.upper().startswith("WEP_ABSORP_POS"):
                if a.ids and rid not in a.ids:
                    continue
                print("  " + _absorp_line(rid, _fmt_row(g, addr)))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info")
    sub.add_parser("params")

    d = sub.add_parser("dump")
    d.add_argument("needle")
    d.add_argument("--raw", type=int, default=0, help="also hexdump N bytes per row")
    d.add_argument("--ids", type=int, nargs="*", default=None)

    args = ap.parse_args()
    g = Game()
    {"info": cmd_info, "params": cmd_params, "dump": cmd_dump}[args.cmd](g, args)


if __name__ == "__main__":
    main()
