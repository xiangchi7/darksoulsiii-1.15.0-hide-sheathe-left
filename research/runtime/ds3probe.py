#!/usr/bin/env python3
"""Read/write/scan helpers for a live DarkSoulsIII.exe (1.15.0).

Usage examples:
    py ds3probe.py pid
    py ds3probe.py chains
    py ds3probe.py u8  0x7FF49E8A0990+0x2C8
    py ds3probe.py dump 0x7FF49F14AAB0 256
    py ds3probe.py scan 0x7FF49F14AAB0 0x10000000

Only stdlib (ctypes) is used.
"""

import ctypes
import ctypes.wintypes as wt
import re
import struct
import sys

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

GAME_BASE = 0x140000000

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.ReadProcessMemory.restype = wt.BOOL
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.restype = wt.BOOL
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.CloseHandle.argtypes = [wt.HANDLE]

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD),
                ("cntUsage", wt.DWORD),
                ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


def find_pid(name="DarkSoulsIII.exe"):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wt.HANDLE(-1).value or snap is None:
        return None
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    ok = k32.Process32First(snap, ctypes.byref(entry))
    found = None
    while ok:
        if entry.szExeFile.decode("ascii", "ignore").lower() == name.lower():
            found = entry.th32ProcessID
            break
        ok = k32.Process32Next(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return found


class Game(object):
    def __init__(self, pid=None):
        self.pid = pid or find_pid()
        if not self.pid:
            raise RuntimeError("DarkSoulsIII.exe not running")
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE |
                                 PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION,
                                 False, self.pid)
        if not self.h:
            raise RuntimeError("OpenProcess failed: %d" % ctypes.get_last_error())

    def close(self):
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n,
                                     ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def write(self, addr, data):
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        got = ctypes.c_size_t(0)
        return bool(k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), buf,
                                           len(data), ctypes.byref(got)))

    def u8(self, addr):
        b = self.read(addr, 1)
        return None if b is None else b[0]

    def u16(self, addr):
        b = self.read(addr, 2)
        return None if b is None else struct.unpack("<H", b)[0]

    def i16(self, addr):
        b = self.read(addr, 2)
        return None if b is None else struct.unpack("<h", b)[0]

    def u32(self, addr):
        b = self.read(addr, 4)
        return None if b is None else struct.unpack("<I", b)[0]

    def i32(self, addr):
        b = self.read(addr, 4)
        return None if b is None else struct.unpack("<i", b)[0]

    def u64(self, addr):
        b = self.read(addr, 8)
        return None if b is None else struct.unpack("<Q", b)[0]

    def f32(self, addr):
        b = self.read(addr, 4)
        return None if b is None else struct.unpack("<f", b)[0]

    # ---------------------------------------------------------------- helpers
    def gdm(self):
        """GameDataMan = *(game+0x4740178)"""
        return self.u64(GAME_BASE + 0x4740178)

    def wcm(self):
        """WorldChrMan = *(game+0x4768E78)"""
        return self.u64(GAME_BASE + 0x4768E78)

    def chains(self):
        out = []
        gdm = self.gdm()
        wcm = self.wcm()
        out.append(("GameDataMan", gdm))
        out.append(("WorldChrMan", wcm))

        # ArmStyle: CT says BaseA + 2B8 + 10 ; try every deref interpretation
        cands = []
        if gdm:
            a = self.u64(gdm + 0x2B8)
            if a:
                cands.append(("A  [[gdm]+2B8]+10", self.u8(a + 0x10)))
                b = self.u64(a)
                if b:
                    cands.append(("A2 [[[gdm]+2B8]]+10", self.u8(b + 0x10)))
            cands.append(("C  [gdm+2C8]", self.u8(gdm + 0x2C8)))
        cands.append(("D  *[game+4740178+2B8]+10",
                      self.u8((self.u64(GAME_BASE + 0x4740178 + 0x2B8) or 0) + 0x10)))
        cands.append(("E  [game+4740178+2C8]", self.u8(GAME_BASE + 0x4740178 + 0x2C8)))
        out.append(("ArmStyle candidates", cands))

        # ChrAsm: CT says [[[[[WorldChrMan]+2098]+8]+18]+1F90] and the player is [[WorldChrMan]+80]
        ch = []
        if wcm:
            v1 = self.u64(wcm + 0x2098)
            ch.append(("wcm+2098", v1))
            if v1 and v1 > 0x10000:
                v2 = self.u64(v1 + 8)
                v3 = self.u64(v2 + 0x18) if v2 else None
                v4 = self.u64(v3 + 0x1F90) if v3 else None
                ch.append(("chain", (v1, v2, v3, v4)))
                if v4:
                    ch.append(("enable@+80", self.u8(v4 + 0x80)))
            pl = self.u64(wcm + 0x80)
            ch.append(("player [[wcm]+80]", pl))
            if pl and pl > 0x10000:
                ch.append(("[player+1F90]", self.u64(pl + 0x1F90)))
                ch.append(("[player+1A08..09]", (self.u8(pl + 0x1A08),
                                                 self.u8(pl + 0x1A09))))
        out.append(("ChrAsm candidates", ch))
        return out


def parse_addr(text):
    text = text.strip()
    total = 0
    for part in re.split(r"\+", text):
        part = part.strip()
        if not part:
            continue
        total += int(part, 16) if part.lower().startswith("0x") else int(part, 16)
    return total


def main(argv):
    if len(argv) < 2 or argv[1] == "pid":
        pid = find_pid()
        print("pid =", pid)
        return 0
    g = Game()
    try:
        cmd = argv[1]
        if cmd == "chains":
            for name, value in g.chains():
                print("== %s" % name)
                if isinstance(value, list):
                    for item in value:
                        print("   ", item)
                else:
                    print("    0x%X" % value if isinstance(value, int) and value and value > 0xFFFF
                          else "    %s" % value)
        elif cmd == "paramrow":
            # paramrow <tableAddr> <rowId> [dumpBytes]
            table = parse_addr(argv[2])
            want = int(argv[3], 0)
            nbytes = int(argv[4], 0) if len(argv) > 4 else 0
            head = g.read(table, 0x400)
            if head is None:
                print("table unreadable")
                return 1
            length = struct.unpack("<H", head[0x0A:0x0C])[0]
            name_off = struct.unpack("<Q", head[0x10:0x18])[0]
            name = g.read(table + name_off, 32)
            print("table 0x%X  rows=%d  name=%s" %
                  (table, length, name.split(b"\0")[0].decode("ascii", "ignore")
                   if name else "?"))
            for i in range(length):
                info = g.read(table + 0x40 + i * 0x18, 0x18)
                if not info:
                    break
                rid, roff = struct.unpack("<QQ", info[:16])
                if rid != want:
                    continue
                row = table + roff
                print("  rowId=%d row=0x%X" % (rid, row))
                if nbytes:
                    print(g.read(row, nbytes).hex(" "))
                return 0
            print("  rowId %d not found" % want)
        elif cmd == "chain":
            # chain <startAddr> <off> [<off> ...] : follow *(v + off) at each step
            addr = parse_addr(argv[2])
            val = addr
            print("start 0x%X" % addr)
            for spec in sys.argv[3:]:
                off = int(spec, 0)
                v = g.u64(val)
                if v is None or v < 0x10000:
                    print("  read failed at 0x%X (value %s)" % (val, v))
                    return 1
                nxt = v + off
                print("  [0x%X] = 0x%X  -> +0x%X = 0x%X" % (val, v, off, nxt))
                val = nxt
            print("final 0x%X:" % val)
            blob = g.read(val, 0x60)
            if blob:
                for k in range(0, len(blob), 16):
                    chunk = blob[k:k + 16]
                    print("   %+05X  %-47s  %s" %
                          (k, chunk.hex(" "),
                           "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)))
        elif cmd == "poke":
            # poke <addr> <hex bytes> : write then read back with no delay
            addr = parse_addr(argv[2])
            data = bytes.fromhex("".join(argv[3:]).replace(" ", "").replace("0x", ""))
            before = g.read(addr, len(data))
            ok = g.write(addr, data)
            after = g.read(addr, len(data))
            print("poke 0x%X" % addr)
            print("  before: %s" % (before.hex(" ") if before else "?"))
            print("  wrote : %s  (%s)" % (data.hex(" "), "ok" if ok else "FAILED"))
            print("  right after: %s" % (after.hex(" ") if after else "?"))
        elif cmd == "write":
            # write <addr> <hex bytes>   e.g.  write 0x7FF4AA0B14B8 02000000
            addr = parse_addr(argv[2])
            data = bytes.fromhex("".join(argv[3:]).replace(" ", "").replace("0x", ""))
            ok = g.write(addr, data)
            print("write 0x%X <- %s : %s" % (addr, data.hex(" "), "ok" if ok else "FAILED"))
        elif cmd == "findptr":
            # findptr <start> <size> <lo> <hi>  : 8-byte values inside [lo,hi)
            start = parse_addr(argv[2])
            size = int(argv[3], 0)
            lo = int(argv[4], 0)
            hi = int(argv[5], 0)
            data = g.read(start, size)
            if data is None:
                print("read failed")
                return 1
            print("pointers into [0x%X,0x%X) inside 0x%X+0x%X" % (lo, hi, start, size))
            hits = 0
            for off in range(0, len(data) - 8 + 1, 8):
                v = struct.unpack_from("<Q", data, off)[0]
                if lo <= v < hi:
                    print("   0x%X -> 0x%X" % (start + off, v))
                    hits += 1
                    if hits >= 40:
                        print("   (limit)")
                        break
            print("   %d hit(s)" % hits)
        elif cmd == "snap":
            start = parse_addr(argv[2])
            size = int(argv[3], 0)
            path = argv[4]
            data = g.read(start, size)
            if data is None:
                print("read failed")
                return 1
            with open(path, "wb") as fh:
                fh.write(struct.pack("<QI", start, len(data)))
                fh.write(data)
            print("snapshot %s: 0x%X +0x%X (%d bytes)" % (path, start, len(data), len(data)))
        elif cmd == "diff":
            # diff <fileA> <fileB> [maxHits]
            limit = int(argv[4]) if len(argv) > 4 else 80
            with open(argv[2], "rb") as fh:
                a_hdr = fh.read(12)
                a = fh.read()
            with open(argv[3], "rb") as fh:
                b_hdr = fh.read(12)
                b = fh.read()
            start_a, len_a = struct.unpack("<QI", a_hdr)
            start_b, len_b = struct.unpack("<QI", b_hdr)
            n = min(len(a), len(b))
            frm = to = None
            if "--from" in sys.argv:
                frm = int(sys.argv[sys.argv.index("--from") + 1], 0)
            if "--to" in sys.argv:
                to = int(sys.argv[sys.argv.index("--to") + 1], 0)
            # only report changes in 4-byte aligned words
            runs = []
            off = 0
            while off + 4 <= n:
                if a[off:off + 4] != b[off:off + 4]:
                    if frm is not None or to is not None:
                        addr = start_a + off
                        if (frm is not None and addr < frm) or (to is not None and addr >= to):
                            off += 4
                            continue
                    va = struct.unpack_from("<I", a, off)[0]
                    vb = struct.unpack_from("<I", b, off)[0]
                    runs.append((off, va, vb))
                off += 4
            print("differing 4-byte words: %d (of %d)" % (len(runs), n // 4))
            # interesting = item id range or pointer range
            def interesting(va, vb):
                for v in (va, vb):
                    if 900000 <= v <= 200000000:      # item / model / handle ids
                        return True
                    if 0x7FF000000000 <= v <= 0x7FFFFFFFFFFF:   # heap pointer
                        return True
                return False
            shown = 0
            use_filter = ("--filter" in sys.argv)
            for off, va, vb in runs:
                if use_filter and not interesting(va, vb):
                    continue
                print("  0x%X  %10d -> %-10d   0x%08X -> 0x%08X" %
                      (start_a + off, va, vb, va, vb))
                shown += 1
                if shown >= limit:
                    print("  (limit reached)")
                    break
        elif cmd == "findvals":
            # findvals <start> <size> <width> <v1,v2,...>
            start = parse_addr(argv[2])
            size = int(argv[3], 0)
            width = int(argv[4], 0)
            values = set(int(x, 0) for x in argv[5].split(","))
            data = g.read(start, size)
            if data is None:
                print("read failed (0x%X +0x%X)" % (start, size))
                return 1
            fmt = {1: "<B", 2: "<H", 4: "<I", 8: "<Q"}[width]
            print("scanned 0x%X..0x%X (%d bytes) for %s" %
                  (start, start + size, len(data), sorted(values)))
            hits = {}
            step = 2 if width > 1 else 1
            for off in range(0, len(data) - width + 1, step):
                v = struct.unpack_from(fmt, data, off)[0]
                if v in values:
                    hits.setdefault(v, []).append(start + off)
            for v in sorted(values):
                lst = hits.get(v, [])
                print("  %-10d %d hit(s)%s" %
                      (v, len(lst), (": " + ", ".join("0x%X" % a for a in lst[:12])) if lst else ""))
        elif cmd == "patchall":
            # patchall <tableAddr> <fieldOffset> <hex bytes>  : same field in every row
            table = parse_addr(argv[2])
            foff = int(argv[3], 0)
            data = bytes.fromhex("".join(argv[4:]).replace(" ", "").replace("0x", ""))
            head = g.read(table, 0x40)
            length = struct.unpack("<H", head[0x0A:0x0C])[0]
            ok = 0
            fail = 0
            for i in range(length):
                info = g.read(table + 0x40 + i * 0x18, 0x18)
                if not info:
                    break
                rid, roff = struct.unpack("<QQ", info[:16])
                if g.write(table + roff + foff, data):
                    ok += 1
                else:
                    fail += 1
            print("table 0x%X: wrote %s at +0x%X in %d row(s) (%d failed)" %
                  (table, data.hex(" "), foff, ok, fail))
        elif cmd == "dumpabsorb":
            # dumpabsorb <tableAddr> [--all]  : key fields of every WepAbsorpPos row
            table = parse_addr(argv[2])
            head = g.read(table, 0x40)
            length = struct.unpack("<H", head[0x0A:0x0C])[0]
            print("rows=%d  (rowId hang bind wit[4]  right4 left4 rightBoth4 leftHang4 rightHang4)" % length)
            for i in range(length):
                info = g.read(table + 0x40 + i * 0x18, 0x18)
                if not info:
                    break
                rid, roff = struct.unpack("<QQ", info[:16])
                row = table + roff
                b = g.read(row, 0x60)
                if not b or len(b) < 0x30:
                    continue
                hang, bind = b[0], b[1]
                wit = list(struct.unpack_from("<4b", b, 0x2C))
                groups = [struct.unpack_from("<4H", b, 4 + gi * 8) for gi in range(5)]
                if wit == [0, 0, 0, 0] and hang == 1 and bind == 0 and "--all" not in sys.argv:
                    continue
                print("  %-4d %-4d %-4d wit=%-18s R=%s L=%s RB=%s LH=%s RH=%s" %
                      (rid, hang, bind, str(wit), groups[0], groups[1], groups[2], groups[3], groups[4]))
        elif cmd == "paramwrite":
            # paramwrite <tableAddr> <rowId> <fieldOffset> <hex bytes>
            table = parse_addr(argv[2])
            want = int(argv[3], 0)
            foff = int(argv[4], 0)
            data = bytes.fromhex("".join(argv[5:]).replace(" ", "").replace("0x", ""))
            head = g.read(table, 0x40)
            length = struct.unpack("<H", head[0x0A:0x0C])[0]
            for i in range(length):
                info = g.read(table + 0x40 + i * 0x18, 0x18)
                if not info:
                    break
                rid, roff = struct.unpack("<QQ", info[:16])
                if rid != want:
                    continue
                addr = table + roff + foff
                before = g.read(addr, len(data))
                ok = g.write(addr, data)
                after = g.read(addr, len(data))
                print("table 0x%X row %d +0x%X -> 0x%X : %s -> %s -> %s (%s)" %
                      (table, rid, foff, addr,
                       before.hex(" ") if before else "?",
                       data.hex(" "),
                       after.hex(" ") if after else "?",
                       "ok" if ok else "FAILED"))
                return 0
            print("table 0x%X: row %d not found" % (table, want))
        elif cmd == "paramfindi":
            # paramfindi <tableAddr> <fieldOffset> <intValue> <width> [maxHits]
            table = parse_addr(argv[2])
            foff = int(argv[3], 0)
            want = int(argv[4], 0)
            width = int(argv[5]) if len(argv) > 5 else 2
            limit = int(argv[6]) if len(argv) > 6 else 25
            head = g.read(table, 0x40)
            length = struct.unpack("<H", head[0x0A:0x0C])[0]
            name_off = struct.unpack("<Q", head[0x10:0x18])[0]
            name = g.read(table + name_off, 32)
            print("table 0x%X rows=%d name=%s field@0x%X == %d (width %d)" %
                  (table, length, name.split(b"\0")[0].decode("ascii", "ignore"),
                   foff, want, width))
            hits = 0
            for i in range(length):
                info = g.read(table + 0x40 + i * 0x18, 0x18)
                if not info:
                    break
                rid, roff = struct.unpack("<QQ", info[:16])
                row = table + roff
                if width == 1:
                    val = g.u8(row + foff)
                elif width == 2:
                    val = g.u16(row + foff)
                elif width == 4:
                    val = g.u32(row + foff)
                else:
                    val = g.u64(row + foff)
                if val != want:
                    continue
                print("  rowId=%-9d row=0x%X weight@0C=%s absorb=%s modelId@B8=%s absorpId@170=%s" %
                      (rid, row, g.f32(row + 0x0C),
                       [g.f32(row + 0x30), g.f32(row + 0x34), g.f32(row + 0x38), g.f32(row + 0x3C)],
                       g.u16(row + 0xB8), g.i32(row + 0x170)))
                hits += 1
                if hits >= limit:
                    print("  (limit)")
                    break
            print("  %d hit(s)" % hits)
        elif cmd == "paramfind":
            # paramfind <tableAddr> <fieldOffset> <floatValue> [maxHits]
            table = parse_addr(argv[2])
            foff = int(argv[3], 0)
            want = float(argv[4])
            limit = int(argv[5]) if len(argv) > 5 else 20
            head = g.read(table, 0x40)
            length = struct.unpack("<H", head[0x0A:0x0C])[0]
            name_off = struct.unpack("<Q", head[0x10:0x18])[0]
            name = g.read(table + name_off, 32)
            print("table 0x%X rows=%d name=%s" %
                  (table, length, name.split(b"\0")[0].decode("ascii", "ignore")))
            hits = 0
            for i in range(length):
                info = g.read(table + 0x40 + i * 0x18, 0x18)
                if not info:
                    break
                rid, roff = struct.unpack("<QQ", info[:16])
                row = table + roff
                val = g.f32(row + foff)
                if val is None or abs(val - want) > 0.0001:
                    continue
                mid = g.i16(row + 0xB8)
                guard = [g.f32(row + 0x30), g.f32(row + 0x34),
                         g.f32(row + 0x38), g.f32(row + 0x3C)]
                print("  rowId=%-9d row=0x%X modelId=%-6s guard=%s" %
                      (rid, row, mid, guard))
                hits += 1
                if hits >= limit:
                    print("  (limit reached)")
                    break
            print("  %d hit(s)" % hits)
        elif cmd == "find":
            start = parse_addr(argv[2])
            size = int(argv[3], 0)
            value = int(argv[4], 0)
            width = int(argv[5]) if len(argv) > 5 else 2
            data = g.read(start, size)
            if data is None:
                print("read failed")
                return 1
            hits = 0
            step = 1
            for off in range(0, len(data) - width + 1, step):
                chunk = data[off:off + width]
                if width == 1:
                    v = chunk[0]
                elif width == 2:
                    v = struct.unpack("<H", chunk)[0]
                else:
                    v = struct.unpack("<I", chunk)[0]
                if v == value:
                    print("  hit at 0x%X" % (start + off))
                    hits += 1
                    if hits >= 60:
                        print("  (stopping at 60 hits)")
                        break
            print("  %d hit(s), width=%d" % (hits, width))
        elif cmd == "dump":
            addr = parse_addr(argv[2])
            n = int(argv[3], 0) if len(argv) > 3 else 128
            data = g.read(addr, n)
            if data is None:
                print("read failed")
                return 1
            for off in range(0, len(data), 16):
                chunk = data[off:off + 16]
                hexs = " ".join("%02X" % b for b in chunk)
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                print("  %08X+%03X  %-47s  %s" % (addr, off, hexs, asc))
        elif cmd in ("u8", "u16", "u32", "u64", "i32", "f32"):
            addr = parse_addr(argv[2])
            print("%s(0x%X) = %s" % (cmd, addr, getattr(g, cmd)(addr)))
        else:
            print(__doc__)
    finally:
        g.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
