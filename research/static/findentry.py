import sys, pefile, capstone
pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
secs = [(s.VirtualAddress, s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData), s.PointerToRawData, s.Characteristics) for s in pe.sections]
data = open(sys.argv[1],'rb').read()
def foff(rva):
    for va,end,raw,ch in secs:
        if va <= rva < end: return raw + (rva-va)
    return None
lo, hi = 0xE34D00, 0xE35100
blob = data[foff(lo):foff(lo)+(hi-lo)]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
# candidate function entries: push rdi; sub rsp,0x40  (40 57 48 83 EC 40) or push rbx/rbp variants
import re
pats = [b"\x40\x57\x48\x83\xec\x40", b"\x40\x55\x48\x83\xec\x40", b"\x48\x89\x5c\x24\x08\x57\x48\x83\xec\x40"]
for p in pats:
    i = 0
    while True:
        i = blob.find(p, i)
        if i < 0: break
        rva = lo + i
        print("\n#### candidate entry at exe+%X (pattern %s)" % (rva, p.hex()))
        start = max(0, i-0x10)
        for ins in md.disasm(blob[start:start+0x150], base+lo+start):
            print("   exe+%08X  %-20s %s %s" % (ins.address-base, ins.bytes.hex(), ins.mnemonic, ins.op_str))
        i += 1
