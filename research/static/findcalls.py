#!/usr/bin/env python3
"""Find every `call <rva>` site in the exe and disassemble around it.

usage: py findcalls.py <exe> <rva> [ctxBefore] [ctxAfter]
"""

import sys

import capstone
import pefile


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sections = [(s.VirtualAddress, s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData)
                for s in pe.sections]
    with open(sys.argv[1], "rb") as f:
        data = f.read()

    def file_off(rva):
        for va, end, raw in sections:
            if va <= rva < end:
                return raw + (rva - va)
        return None

    target = base + int(sys.argv[2], 16)
    before = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x30
    after = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x40

    # scan the executable sections for E8 rel32 whose target is the function
    sites = []
    for va, end, raw in sections:
        if not (pe.sections[[s.VirtualAddress for s in pe.sections].index(va)].Characteristics & 0x20000000):
            continue
        blob = data[raw:raw + (end - va)]
        i = 0
        while True:
            i = blob.find(b"\xe8", i)
            if i < 0 or i + 5 > len(blob):
                break
            rel = int.from_bytes(blob[i + 1:i + 5], "little", signed=True)
            site = va + i
            if base + site + 5 + rel == target:
                sites.append(site)
            i += 1

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    print("call sites for exe+0x%X: %d" % (int(sys.argv[2], 16), len(sites)))
    for site in sites:
        start = site - before
        off = file_off(start)
        print("\n---- call at exe+%08X ----" % site)
        blob = data[off:off + before + after]
        for ins in md.disasm(blob, base + start):
            mark = "  <<< CALL" if ins.address == base + site else ""
            print("  exe+%08X  %-22s %s %s%s" % (ins.address - base, ins.bytes.hex(), ins.mnemonic, ins.op_str, mark))


if __name__ == "__main__":
    main()
