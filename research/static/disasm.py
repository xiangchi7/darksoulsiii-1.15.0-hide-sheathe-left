#!/usr/bin/env python3
"""Disassemble ranges of DarkSoulsIII.exe by RVA (address - image base).

usage: py disasm.py <exe> <rva> [before] [after] [moreRvas...]
   e.g. py disasm.py DarkSoulsIII.exe 0x990B60 0x60 0x120 0xE3174B
"""

import sys

import capstone
import pefile


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sections = [(s.VirtualAddress, s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData),
                 s.PointerToRawData) for s in pe.sections]
    with open(sys.argv[1], "rb") as f:
        data = f.read()

    def file_off(rva):
        for va, end, raw in sections:
            if va <= rva < end:
                return raw + (rva - va)
        return None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False

    rvas = []
    i = 2
    while i < len(sys.argv):
        rva = int(sys.argv[i], 16)
        before = int(sys.argv[i + 1], 16) if i + 1 < len(sys.argv) else 0x60
        after = int(sys.argv[i + 2], 16) if i + 2 < len(sys.argv) else 0x100
        # allow "0xE3174B" plus optional sizes, but treat later bare RVAs as new targets
        rvas.append((rva, before, after))
        i += 3

    for rva, before, after in rvas:
        start = rva - before
        off = file_off(start)
        print("\n================ RVA 0x%X (dump 0x%X..0x%X) ================" % (rva, start, rva + after))
        if off is None:
            print("  (rva not in any section)")
            continue
        blob = data[off:off + before + after]
        for ins in md.disasm(blob, base + start):
            mark = "  <<<" if ins.address <= base + rva < ins.address + ins.size else ""
            print("  exe+%08X  %-24s %s %s%s" % (ins.address - base, ins.bytes.hex(), ins.mnemonic, ins.op_str, mark))


if __name__ == "__main__":
    main()
