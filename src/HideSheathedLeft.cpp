// ============================================================================
//  HideSheathedLeft  --  Dark Souls III 1.15.0 (Steam)
// ----------------------------------------------------------------------------
//  Effect: when the item held in the LEFT hand is in its "sheathed" state
//  (the classic case: the player two-hands the right-hand weapon, so the left
//  weapon/shield would normally be shown hanging on the back), its model is
//  hidden completely instead.
//
//  Mechanism (verified in game and against DSAnimStudio's reimplementation of
//  the engine's character assembler):
//
//    The param WepAbsorpPosParam ("WEP_ABSORP_POS_PARAM_ST") stores, for every
//    weapon and every model 0..3, the dummy-poly id the model is attached to in
//    each stance.  The engine picks the cluster purely from the weapon style:
//        OneHand   : left slot -> Left       right slot -> Right
//        RightBoth : left slot -> LeftHang   right slot -> RightBoth
//        LeftBoth  : left slot -> LeftBoth   right slot -> RightHang
//    If the chosen dummy poly id is invalid, the engine builds a degenerate
//    (NaN) attachment matrix.  That is the "black triangles + full-screen
//    flicker" failure mode, so this build does NOT use -1 any more: the fields
//    are pointed at a dummy poly that exists but is parked far below the
//    character (appended to the player's own model c0000.flver by the
//    validator tool, see docs/PARKING-DUMMY.md).  The transform is then a
//    perfectly ordinary one, the model is simply never inside the view
//    frustum, so it is culled and never drawn.
//
//    Paired weapons: the spare blade is model 1 of the same weapon; while the
//    weapon is used one-handed in the RIGHT hand that model follows `right_1`
//    (`right_2`/`right_3` for models 2/3), so pointing those at the parking
//    dummy hides it the same way.
//
//  Nothing is code-patched and no function is hooked -- only the param table
//  (heap data) is edited, so there is nothing for Arxan to trip over.
//
//  Every field the mod touches is snapshotted the first time it is seen, so an
//  option can be switched off again at runtime and the original values are put
//  back (no game restart needed).
//
//  Row layout of WEP_ABSORP_POS_PARAM_ST (row size 0x60):
//      0x04 right_0   0x0E right_1   0x18 right_2   0x22 right_3
//      0x0A leftHang_0 0x14 leftHang_1 0x1E leftHang_2 0x28 leftHang_3
// ============================================================================

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr char     kParamName[]   = "WEP_ABSORP_POS_PARAM_ST";
constexpr uint64_t kLengthOff     = 0x0A;   // u16 row count inside ParamTable
constexpr uint64_t kNameOffsetOff = 0x10;   // u64 offset of the snake-case name
constexpr uint64_t kRowInfoOff    = 0x40;   // ParamRowInfo[] { u64 id, u64 off, u64 unk }
constexpr uint64_t kRowInfoSize   = 0x18;
constexpr uint32_t kMaxRows       = 40000;
constexpr uint32_t kRowSize       = 0x60;
constexpr uint16_t kInvalidPoly   = 0xFFFF; // -1 as s16: degenerate matrix, avoid it
constexpr int      kParkPolyDefault = 382;  // parking dummy appended to EVERY character
                                            // model by the model patch (1 km below)
constexpr uint32_t kScanChunk     = 4u << 20;
constexpr uint64_t kResolveWindow = 0x100000;

// The fields the mod manages: 4 left-hang slots + 3 paired off-hand models.
constexpr int kFieldCount = 7;
const int  kFieldOff[kFieldCount] = {0x0A, 0x14, 0x1E, 0x28, 0x0E, 0x18, 0x22};
const bool kFieldIsLeftHang[kFieldCount] = {true, true, true, true,
                                            false, false, false};

struct Config {
    bool hideLeftHang      = true;
    bool hidePairedOffhand = true;
    bool log               = true;
    int  intervalMs        = 1000;  // 1 s: keeps the window in which the engine's
                                    // own (vanilla) values could be live as short
                                    // as possible after any param-table reload
    int  hidePoly          = kParkPolyDefault;  // -1 = old behaviour (invalid poly)
    // which models of the RIGHT hand are hidden while it is used one-handed:
    // 1 = the spare blade (paired weapons), 2/3 = the scabbard/extra models some
    // weapons carry -- those are deliberately opt-in
    bool paired1           = true;
    bool paired2           = true;
    bool paired3           = true;
    // Probe=1: write NOTHING.  Instead put PAGE_GUARD on the pages that hold the
    // WepAbsorpPosParam row data and log who reads them (RIP, registers, the
    // faulting offset) -- used to locate the engine's attach resolver so the mod
    // can later be made player-only.
    bool probe             = false;
    bool probeAll          = false;   // log every table access, not just leftHang/right1-3
    uint64_t worldChrManOffset = 0x4768E78;   // candidate WorldChrMan pointer (1.15.0), 0 = off
    int  probeLimit        = 500;
    int  probeRearmMs      = 100;
};

struct TableState {
    uint64_t addr       = 0;
    uint16_t len        = 0;
    uint64_t nameOffset = 0;
    bool     valid      = false;
    std::vector<uint8_t>  have;   // per row: snapshot taken?
    std::vector<uint16_t> orig;   // per row: kFieldCount original values
};

Config       g_cfg;
std::wstring g_iniPath;
std::wstring g_logPath;
CRITICAL_SECTION g_logLock;
bool         g_logLockReady = false;
bool         g_loggedConfig = false;

// ---------------------------------------------------------------- utilities
bool SafeCopy(void* dst, const void* src, size_t n) {
    __try {
        memcpy(dst, src, n);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

void Log(const char* fmt, ...) {
    if (!g_cfg.log || !g_logLockReady) return;
    EnterCriticalSection(&g_logLock);
    if (FILE* f = _wfopen(g_logPath.c_str(), L"a, ccs=UTF-8")) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fwprintf(f, L"[%02d:%02d:%02d] ", st.wHour, st.wMinute, st.wSecond);
        char buf[1024];
        va_list ap;
        va_start(ap, fmt);
        _vsnprintf_s(buf, sizeof(buf), _TRUNCATE, fmt, ap);
        va_end(ap);
        fwprintf(f, L"%hs\n", buf);
        fclose(f);
    }
    LeaveCriticalSection(&g_logLock);
}

std::wstring ModuleDir(HMODULE mod) {
    wchar_t path[MAX_PATH] = {0};
    GetModuleFileNameW(mod, path, MAX_PATH);
    std::wstring s(path);
    size_t p = s.find_last_of(L"\\/");
    return (p == std::wstring::npos) ? std::wstring(L".") : s.substr(0, p);
}

void LoadConfig() {
    Config c;
    c.hideLeftHang      = GetPrivateProfileIntW(L"general", L"HideLeftHang", 1, g_iniPath.c_str()) != 0;
    c.hidePairedOffhand = GetPrivateProfileIntW(L"general", L"HidePairedOffhand", 1, g_iniPath.c_str()) != 0;
    c.log               = GetPrivateProfileIntW(L"general", L"Log", 1, g_iniPath.c_str()) != 0;
    // Re-applied every IntervalSeconds.  The engine can rewrite these fields from
    // its own regulation data (equipment change, area transition, param reload);
    // until the next pass the vanilla value is live, so this interval is the
    // longest a "sheathed item pops back for a moment" window can last.
    int sec = (int)GetPrivateProfileIntW(L"general", L"IntervalSeconds", 1, g_iniPath.c_str());
    if (sec < 1) sec = 1;
    if (sec > 600) sec = 600;
    c.intervalMs = sec * 1000;

    int poly = (int)GetPrivateProfileIntW(L"general", L"HidePoly", kParkPolyDefault, g_iniPath.c_str());
    if (poly < -1) poly = -1;
    if (poly > 32000) poly = 32000;
    c.hidePoly = poly;

    // PairedFields = which right-hand model indices to park, e.g. "1" or "1,2,3".
    // Anything not listed is left at its original value.
    wchar_t pf[64] = {0};
    GetPrivateProfileStringW(L"general", L"PairedFields", L"1,2,3", pf, 63, g_iniPath.c_str());
    c.paired1 = c.paired2 = c.paired3 = false;
    for (const wchar_t* q = pf; *q; ++q) {
        if (*q == L'1') c.paired1 = true;
        else if (*q == L'2') c.paired2 = true;
        else if (*q == L'3') c.paired3 = true;
    }
    if (!c.paired1 && !c.paired2 && !c.paired3 && wcsstr(pf, L"none") == nullptr) {
        c.paired1 = true;  // unparsable value: fall back to the spare blade only
    }

    c.probe        = GetPrivateProfileIntW(L"general", L"Probe", 0, g_iniPath.c_str()) != 0;
    c.probeAll     = GetPrivateProfileIntW(L"general", L"ProbeAll", 0, g_iniPath.c_str()) != 0;
    wchar_t wcm[32] = {0};
    GetPrivateProfileStringW(L"general", L"WorldChrManOffset", L"0x4768E78", wcm, 31, g_iniPath.c_str());
    c.worldChrManOffset = wcstoull(wcm, nullptr, 0);
    int pl         = (int)GetPrivateProfileIntW(L"general", L"ProbeLimit", 500, g_iniPath.c_str());
    if (pl < 1) pl = 1;
    if (pl > 5000) pl = 5000;
    c.probeLimit   = pl;
    int pr         = (int)GetPrivateProfileIntW(L"general", L"ProbeRearmMs", 100, g_iniPath.c_str());
    if (pr < 10) pr = 10;
    if (pr > 2000) pr = 2000;
    c.probeRearmMs = pr;

    const bool changed = (c.hideLeftHang != g_cfg.hideLeftHang) ||
                         (c.hidePairedOffhand != g_cfg.hidePairedOffhand) ||
                         (c.intervalMs != g_cfg.intervalMs) ||
                         (c.hidePoly != g_cfg.hidePoly) ||
                         (c.paired1 != g_cfg.paired1) ||
                         (c.paired2 != g_cfg.paired2) ||
                         (c.paired3 != g_cfg.paired3) ||
                         (c.probe != g_cfg.probe) ||
                         (c.probeAll != g_cfg.probeAll) ||
                         (c.probeLimit != g_cfg.probeLimit) ||
                         (c.log != g_cfg.log);
    g_cfg = c;
    // always report the effective configuration once, so the log shows which dummy
    // the fields are pointed at even when nothing was changed from the defaults
    if (changed || !g_loggedConfig) {
        g_loggedConfig = true;
        Log("config: HideLeftHang=%d HidePairedOffhand=%d PairedFields=%d%d%d IntervalSeconds=%d Log=%d HidePoly=%d Probe=%d",
            (int)g_cfg.hideLeftHang, (int)g_cfg.hidePairedOffhand,
            (int)g_cfg.paired1, (int)g_cfg.paired2, (int)g_cfg.paired3,
            g_cfg.intervalMs / 1000, (int)g_cfg.log, g_cfg.hidePoly, (int)g_cfg.probe);
    }
}

// ------------------------------------------------------- param table access
bool ResolveTableFromName(uint64_t nameAddr, uint64_t* outTable) {
    if (nameAddr <= kResolveWindow) return false;
    const uint64_t start  = nameAddr - kResolveWindow;
    const size_t   strIdx = (size_t)(nameAddr - start);
    const size_t   n      = strIdx + 16;
    std::vector<uint8_t> buf(n);
    if (!SafeCopy(buf.data(), (const void*)start, n)) return false;

    for (uint64_t delta = kRowInfoOff; delta + 0x18 <= n && delta <= strIdx; ++delta) {
        const size_t base = strIdx - (size_t)delta;
        uint64_t nameOffset = 0;
        memcpy(&nameOffset, buf.data() + base + kNameOffsetOff, 8);
        if (nameOffset != delta) continue;
        uint16_t len = 0;
        memcpy(&len, buf.data() + base + kLengthOff, 2);
        if (len == 0 || len > kMaxRows) continue;
        *outTable = start + base;
        return true;
    }
    return false;
}

bool ValidateTable(TableState& st, char* nameOut, size_t nameOutSize) {
    uint16_t len = 0;
    if (!SafeCopy(&len, (const void*)(st.addr + kLengthOff), 2)) return false;
    if (len == 0 || len > kMaxRows) return false;
    uint64_t nameOffset = 0;
    if (!SafeCopy(&nameOffset, (const void*)(st.addr + kNameOffsetOff), 8)) return false;
    if (nameOffset < kRowInfoOff || nameOffset > kResolveWindow) return false;
    char name[64] = {0};
    if (!SafeCopy(name, (const void*)(st.addr + nameOffset), sizeof(name) - 1)) return false;
    if (strcmp(name, kParamName) != 0) return false;
    st.len = len;
    st.nameOffset = nameOffset;
    st.valid = true;
    if (nameOut) {
        strncpy_s(nameOut, nameOutSize, name, _TRUNCATE);
    }
    return true;
}

// Apply the current config to one table, snapshotting originals on first sight
// so options can be turned off again at runtime.  Values are only written when
// they actually differ, so after the first pass the mod is completely passive.
int ApplyTable(TableState& st, int* writesOut) {
    if (!ValidateTable(st, nullptr, 0)) return -1;

    if (st.have.size() != st.len) {
        st.have.assign(st.len, 0);
        st.orig.assign((size_t)st.len * kFieldCount, 0);
    }

    const uint64_t dataStart = st.addr + kRowInfoOff + (uint64_t)st.len * kRowInfoSize;
    const uint64_t dataEnd   = st.addr + st.nameOffset;
    (void)dataStart;

    int rows = 0, writes = 0;
    for (uint16_t i = 0; i < st.len; ++i) {
        const uint64_t info = st.addr + kRowInfoOff + (uint64_t)i * kRowInfoSize;
        uint64_t rowId = 0, rowOff = 0;
        if (!SafeCopy(&rowId, (const void*)info, 8)) continue;
        if (!SafeCopy(&rowOff, (const void*)(info + 8), 8)) continue;
        const uint64_t row = st.addr + rowOff;
        if (rowOff < kRowInfoOff + (uint64_t)st.len * kRowInfoSize) continue;
        if (row + kRowSize > dataEnd) continue;

        uint8_t* p = (uint8_t*)row;
        if (!st.have[i]) {
            for (int f = 0; f < kFieldCount; ++f) {
                uint16_t v = 0;
                if (!SafeCopy(&v, p + kFieldOff[f], 2)) { v = 0; }
                st.orig[(size_t)i * kFieldCount + f] = v;
            }
            st.have[i] = 1;
        }
        for (int f = 0; f < kFieldCount; ++f) {
            // f 0..3 = leftHang_0..3, f 4..6 = right_1..3
            const bool enabled = kFieldIsLeftHang[f]
                                     ? g_cfg.hideLeftHang
                                     : (g_cfg.hidePairedOffhand &&
                                        (f == 4 ? g_cfg.paired1 : f == 5 ? g_cfg.paired2 : g_cfg.paired3));
            const uint16_t park = (g_cfg.hidePoly < 0)
                                      ? kInvalidPoly
                                      : (uint16_t)(int16_t)g_cfg.hidePoly;
            const uint16_t target = enabled ? park
                                            : st.orig[(size_t)i * kFieldCount + f];
            uint16_t cur = 0;
            if (SafeCopy(&cur, p + kFieldOff[f], 2) && cur == target) continue;
            *(uint16_t*)(p + kFieldOff[f]) = target;
            ++writes;
        }
        ++rows;
    }
    if (writesOut) *writesOut += writes;
    return rows;
}

std::vector<uint64_t> ScanForTables() {
    std::vector<uint64_t> found;
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    const size_t nameLen = sizeof(kParamName) - 1;
    std::vector<uint8_t> buf(kScanChunk + nameLen);

    uint8_t* addr = (uint8_t*)si.lpMinimumApplicationAddress;
    const uint8_t* maxAddr = (const uint8_t*)si.lpMaximumApplicationAddress;

    while (addr < maxAddr) {
        MEMORY_BASIC_INFORMATION mbi;
        if (!VirtualQuery(addr, &mbi, sizeof(mbi))) break;
        uint8_t* base = (uint8_t*)mbi.BaseAddress;
        const size_t size = mbi.RegionSize;

        const bool usable = mbi.State == MEM_COMMIT &&
                            (mbi.Type == MEM_PRIVATE || mbi.Type == MEM_MAPPED) &&
                            !(mbi.Protect & PAGE_GUARD) && !(mbi.Protect & PAGE_NOACCESS);
        if (usable && size) {
            for (size_t off = 0; off < size; off += kScanChunk) {
                size_t n = size - off;
                if (n > kScanChunk + nameLen) n = kScanChunk + nameLen;
                if (!SafeCopy(buf.data(), base + off, n)) continue;

                size_t i = 0;
                while (i + nameLen <= n) {
                    void* hit = memchr(buf.data() + i, kParamName[0], n - i - (nameLen - 1));
                    if (!hit) break;
                    const size_t idx = (size_t)((uint8_t*)hit - buf.data());
                    if (memcmp(buf.data() + idx, kParamName, nameLen) == 0) {
                        uint64_t table = 0;
                        if (ResolveTableFromName((uint64_t)(base + off + idx), &table)) {
                            bool dup = false;
                            for (uint64_t t : found) if (t == table) { dup = true; break; }
                            if (!dup) found.push_back(table);
                        }
                    }
                    i = idx + 1;
                }
            }
        }
        if (!size) break;
        addr = base + size;
    }
    return found;
}

// ------------------------------------------------------- engine-reader probe
// Probe=1 writes nothing at all.  Instead it puts PAGE_GUARD on the pages holding
// the WepAbsorpPosParam row data and logs every access (RIP, registers, faulting
// offset).  That locates the engine's attach/dummy resolver from outside, which is
// the prerequisite for making the effect player-only (hook that site and only use
// the parking dummy for the player's ChrAsm).
//
// Two details are load-bearing:
//  * Windows clears the guard bit when it raises the exception, so a page fires
//    once per arming.  The faulting instruction must NOT be re-armed inside the
//    handler (that would trap forever) -- the worker re-arms every ProbeRearmMs.
//  * Every guard exception on a page we own has to be swallowed with
//    CONTINUE_EXECUTION, otherwise the process dies with a guard-page violation;
//    so the handler answers for all of ours and only logs the ones that fall in a
//    table's row data.

struct ProbeRange { uint64_t begin, end, table; };
struct ProbeRow   { uint64_t addr; uint64_t id; uint64_t table; };

std::vector<ProbeRange> g_probeRanges;
std::vector<ProbeRow>   g_probeRows;
std::vector<uint64_t>   g_probePages;
std::vector<DWORD>      g_probeProt;
volatile LONG           g_probeEvents = 0;
volatile LONG           g_probeHits = 0;
volatile LONG           g_probeStackLogged = 0;
uint64_t                g_probeStepPageAddr = 0;   // page to re-arm on the single-step trap
uint64_t                g_exeBase = 0;
PVOID                   g_probeVeh = nullptr;

// (RIP, field offset) pairs already reported, so the log stays short
struct ProbeSeen { uint64_t rip; int field; };
ProbeSeen g_probeSeen[128];
int       g_probeSeenCount = 0;
volatile LONG g_probeOther = 0;

bool ProbeFieldOfInterest(int off) {
    // Any access that STARTS in the first half of a row can be the attach resolver:
    // the engine may read 2, 4 or 8 byte chunks, so the faulting address is the start
    // of the chunk, not necessarily the exact field.  Offsets 0x00..0x30 cover
    // hangPosType, isSkeletonBind, right_0/left_0/both_0, leftHang_0..3, rightHang_0..3,
    // right_1..3, left_1..3, both_1..3 and leftBoth_0..3.
    return off >= 0 && off <= 0x30;
}

// Find the player's character without any gameplay input: the parking dummies
// 382/383 exist in the player's model only, so locate the appended dummy entries in
// memory and then find who points at them (the loaded model object -> the character
// that owns it).  That gives a per-session rule for "this character is the player",
// which is what the player-only hook needs.
void ProbeScanPlayerModel() {
    const unsigned char needle[4] = { 0x7E, 0x01, 0x7F, 0x01 };   // int16 382, 383
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    uint64_t a = (uint64_t)si.lpMinimumApplicationAddress;
    const uint64_t end = (uint64_t)si.lpMaximumApplicationAddress;
    uint64_t hits[4] = {0};
    int hitCount = 0;
    std::vector<unsigned char> buf(0x10000);
    MEMORY_BASIC_INFORMATION mbi;
    while (a < end && hitCount < 4) {
        if (!VirtualQuery((LPCVOID)a, &mbi, sizeof(mbi))) break;
        const uint64_t regionBase = (uint64_t)mbi.BaseAddress;
        const uint64_t regionSize = mbi.RegionSize;
        const bool readable = mbi.State == MEM_COMMIT && mbi.Type == MEM_PRIVATE &&
            !(mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)) &&
            (mbi.Protect & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE));
        if (readable && regionSize <= 0x40000000) {
            for (uint64_t off = 0; off < regionSize && hitCount < 4; off += buf.size()) {
                const size_t want = (size_t)((regionSize - off) < buf.size() ? (regionSize - off) : buf.size());
                if (!SafeCopy(buf.data(), (const void*)(regionBase + off), want)) continue;
                for (size_t i = 0; i + 4 <= want; ++i) {
                    if (buf[i] == needle[0] && buf[i + 1] == needle[1] &&
                        buf[i + 2] == needle[2] && buf[i + 3] == needle[3]) {
                        hits[hitCount++] = regionBase + off + i;
                        if (hitCount >= 4) break;
                    }
                }
            }
        }
        a = regionBase + regionSize;
    }
    Log("model scan: %d hit(s) for the 382/383 dummy pair", hitCount);
    for (int h = 0; h < hitCount; ++h) {
        const uint64_t hit = hits[h];
        int16_t around[16] = {0};
        if (SafeCopy(around, (const void*)(hit - 16), sizeof(around))) {
            char line[512] = {0};
            int n = 0;
            for (int i = 0; i < 16; ++i)
                n += _snprintf_s(line + n, sizeof(line) - n, _TRUNCATE, "%d ", around[i]);
            Log("  hit %d at 0x%llX, int16 window: %s", h, (unsigned long long)hit, line);
        }
        // who points into the same page? (= the model object holding this dummy array)
        int refs = 0;
        a = (uint64_t)si.lpMinimumApplicationAddress;
        while (a < end && refs < 6) {
            if (!VirtualQuery((LPCVOID)a, &mbi, sizeof(mbi))) break;
            const uint64_t regionBase = (uint64_t)mbi.BaseAddress;
            const uint64_t regionSize = mbi.RegionSize;
            const bool readable = mbi.State == MEM_COMMIT && mbi.Type == MEM_PRIVATE &&
                !(mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)) &&
                (mbi.Protect & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE));
            if (readable && regionSize <= 0x40000000) {
                for (uint64_t off = 0; off < regionSize && refs < 6; off += buf.size()) {
                    const size_t want = (size_t)((regionSize - off) < buf.size() ? (regionSize - off) : buf.size());
                    if (!SafeCopy(buf.data(), (const void*)(regionBase + off), want)) continue;
                    for (size_t i = 0; i + 8 <= want; i += 8) {
                        uint64_t v = 0;
                        memcpy(&v, buf.data() + i, 8);
                        if (v >= (hit & ~(uint64_t)0xFFF) && v < (hit & ~(uint64_t)0xFFF) + 0x1000) {
                            ++refs;
                            Log("    ref to model page: [0x%llX] = 0x%llX", (unsigned long long)(regionBase + off + i), (unsigned long long)v);
                            uint64_t ctx[16] = {0};
                            if (SafeCopy(ctx, (const void*)((regionBase + off + i) & ~(uint64_t)0x3F), sizeof(ctx)))
                                for (int k = 0; k < 16; k += 4)
                                    Log("      ctx: %llX %llX %llX %llX", (unsigned long long)ctx[k],
                                        (unsigned long long)ctx[k + 1], (unsigned long long)ctx[k + 2],
                                        (unsigned long long)ctx[k + 3]);
                            if (refs >= 6) break;
                        }
                    }
                }
            }
            a = regionBase + regionSize;
        }
    }
}

void ProbeDumpWorldChrMan() {    if (!g_cfg.worldChrManOffset) return;
    uint64_t wcm = 0;
    if (!SafeCopy(&wcm, (const void*)(g_exeBase + g_cfg.worldChrManOffset), 8) || wcm < 0x10000) return;
    uint64_t q[64] = {0};
    if (!SafeCopy(q, (const void*)wcm, sizeof(q))) return;
    Log("wcm graph base=0x%llX", (unsigned long long)wcm);
    for (int i = 0; i < 64; ++i) {
        const uint64_t v = q[i];
        if (v > 0x10000 && v < 0x00007FFFFFFFFFFFull && (v & 7) == 0) {
            uint64_t sub[4] = {0};
            if (SafeCopy(sub, (const void*)v, sizeof(sub)))
                Log("  wcm+%03X -> 0x%llX : %llX %llX %llX %llX", i * 8, (unsigned long long)v,
                    (unsigned long long)sub[0], (unsigned long long)sub[1],
                    (unsigned long long)sub[2], (unsigned long long)sub[3]);
        } else {
            Log("  wcm+%03X = 0x%llX", i * 8, (unsigned long long)v);
        }
    }
    // candidate player-pointer slots inside WorldChrMan
    const uint64_t cand[] = { 0x1F90, 0x1E508, 0x1E510, 0x10A0, 0x2C0, 0x14 };
    for (int ci = 0; ci < 6; ++ci) {
        uint64_t v = 0;
        if (!SafeCopy(&v, (const void*)(wcm + cand[ci]), 8) || v < 0x10000) continue;
        Log("  wcm+%llX = 0x%llX", (unsigned long long)cand[ci], (unsigned long long)v);
        uint64_t q[8] = {0};
        if (SafeCopy(q, (const void*)v, sizeof(q)))
            Log("     -> %llX %llX %llX %llX %llX %llX %llX %llX",
                (unsigned long long)q[0], (unsigned long long)q[1], (unsigned long long)q[2],
                (unsigned long long)q[3], (unsigned long long)q[4], (unsigned long long)q[5],
                (unsigned long long)q[6], (unsigned long long)q[7]);
    }
}

LONG CALLBACK ProbeHandler(PEXCEPTION_POINTERS ep) {
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_SINGLE_STEP) {
        // the trap flag fired right after the access we just logged: re-arm that page
        if (g_probeStepPageAddr) {
            for (size_t i = 0; i < g_probePages.size(); ++i)
                if (g_probePages[i] == g_probeStepPageAddr) {
                    DWORD old = 0;
                    VirtualProtect((LPVOID)g_probePages[i], 0x1000, g_probeProt[i] | PAGE_GUARD, &old);
                    break;
                }
            g_probeStepPageAddr = 0;
        }
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_GUARD_PAGE) return EXCEPTION_CONTINUE_SEARCH;
    const uint64_t fault = (uint64_t)ep->ExceptionRecord->ExceptionInformation[1];
    const uint64_t page = fault & ~(uint64_t)0xFFF;
    bool ours = false;
    for (size_t i = 0; i < g_probePages.size(); ++i) if (g_probePages[i] == page) { ours = true; break; }
    if (!ours) return EXCEPTION_CONTINUE_SEARCH;
    const LONG seq = InterlockedIncrement(&g_probeEvents);

    // map the touched address to (row, field offset) -- exact, via the row info array
    uint64_t rowId = 0;
    int off = -1;
    for (size_t i = 0; i < g_probeRows.size(); ++i) {
        const ProbeRow& r = g_probeRows[i];
        if (fault >= r.addr && fault < r.addr + kRowSize) {
            rowId = r.id;
            off = (int)(fault - r.addr);
            break;
        }
    }

    const CONTEXT* c = ep->ContextRecord;
    // One-shot stack walk on the first leftHang read: the hang-dummy selector
    // (exe+0xE31690) is a generic param accessor, so the character is a frame or two
    // up.  Dumping the raw stack + saved frame pointers is how we find it.
    if (off == 0x0A && (uint64_t)(c->Rip - g_exeBase) == 0xE316AC &&
        InterlockedIncrement(&g_probeStackLogged) <= 3) {
        Log("STACK selector rsp=0x%llX rbx=%llX rbp=%llX rdi=%llX rsi=%llX r10=0x%llX r12=%llX r13=%llX r14=%llX r15=%llX",
            (unsigned long long)c->Rsp, (unsigned long long)c->Rbx, (unsigned long long)c->Rbp,
            (unsigned long long)c->Rdi, (unsigned long long)c->Rsi, (unsigned long long)c->R10,
            (unsigned long long)c->R12, (unsigned long long)c->R13,
            (unsigned long long)c->R14, (unsigned long long)c->R15);
        uint64_t st[32] = {0};
        if (SafeCopy(st, (const void*)c->Rsp, sizeof(st)))
            for (int i = 0; i < 32; i += 4)
                Log("  stack+%02X: 0x%llX 0x%llX 0x%llX 0x%llX", i * 8,
                    (unsigned long long)st[i], (unsigned long long)st[i + 1],
                    (unsigned long long)st[i + 2], (unsigned long long)st[i + 3]);
        ProbeDumpWorldChrMan();
    }
    if (ProbeFieldOfInterest(off) && seq <= (LONG)g_cfg.probeLimit) {
        uint32_t val32 = 0;
        SafeCopy(&val32, (const void*)fault, 4);
        uint64_t ret0 = 0, ret1 = 0, ret2 = 0;
        SafeCopy(&ret0, (const void*)c->Rsp, 8);
        SafeCopy(&ret1, (const void*)(c->Rsp + 8), 8);
        SafeCopy(&ret2, (const void*)(c->Rsp + 16), 8);
        Log("SEQ %ld row=0x%llX off=+0x%X val32=0x%08X RIP=0x%llX (exe+0x%llX) rcx=0x%llX rdx=0x%llX r8=0x%llX r9=0x%llX ret=0x%llX,0x%llX,0x%llX",
            (long)seq, (unsigned long long)rowId, off < 0 ? 0 : off, val32,
            (unsigned long long)c->Rip, (unsigned long long)(g_exeBase ? c->Rip - g_exeBase : 0),
            (unsigned long long)c->Rcx, (unsigned long long)c->Rdx,
            (unsigned long long)c->R8, (unsigned long long)c->R9,
            (unsigned long long)ret0, (unsigned long long)ret1, (unsigned long long)ret2);
    } else if (g_cfg.probeAll && InterlockedIncrement(&g_probeOther) <= (LONG)g_cfg.probeLimit) {
        Log("PROBE-ALL fault=0x%llX row=0x%llX off=0x%X RIP=0x%llX (exe+0x%llX) rcx=0x%llX rdx=0x%llX",
            (unsigned long long)fault, (unsigned long long)rowId, off < 0 ? 0 : off,
            (unsigned long long)c->Rip, (unsigned long long)(g_exeBase ? c->Rip - g_exeBase : 0),
            (unsigned long long)c->Rcx, (unsigned long long)c->Rdx);
    }

    // catch EVERY access, not just the first per re-arm: single-step once so the page
    // can be re-armed after the faulting instruction has executed (re-arming inside
    // this handler would trap on the same instruction forever)
    if (g_probeStepPageAddr == 0 && seq <= (LONG)g_cfg.probeLimit * 4) {
        g_probeStepPageAddr = page;
        ep->ContextRecord->EFlags |= 0x100;   // trap flag
    }
    return EXCEPTION_CONTINUE_EXECUTION;
}

void ArmProbePages() {
    for (size_t i = 0; i < g_probePages.size(); ++i) {
        DWORD old = 0;
        VirtualProtect((LPVOID)g_probePages[i], 0x1000, g_probeProt[i] | PAGE_GUARD, &old);
    }
}

int PrepareProbe(std::vector<TableState>& tables) {
    for (TableState& st : tables) {
        if (!ValidateTable(st, nullptr, 0)) continue;
        const uint64_t dataStart = st.addr + kRowInfoOff + (uint64_t)st.len * kRowInfoSize;
        const uint64_t dataEnd   = st.addr + st.nameOffset;
        if (dataEnd <= dataStart) continue;
        ProbeRange r = { dataStart, dataEnd, st.addr };
        g_probeRanges.push_back(r);
        for (uint16_t i = 0; i < st.len; ++i) {
            uint64_t id = 0, rowOff = 0;
            const uint64_t info = st.addr + kRowInfoOff + (uint64_t)i * kRowInfoSize;
            if (!SafeCopy(&id, (const void*)info, 8)) continue;
            if (!SafeCopy(&rowOff, (const void*)(info + 8), 8)) continue;
            const uint64_t row = st.addr + rowOff;
            if (row < dataStart || row + kRowSize > dataEnd) continue;
            ProbeRow pr = { row, id, st.addr };
            g_probeRows.push_back(pr);
        }
        for (uint64_t a = dataStart & ~(uint64_t)0xFFF; a < dataEnd; a += 0x1000) {
            bool dup = false;
            for (size_t k = 0; k < g_probePages.size(); ++k) if (g_probePages[k] == a) { dup = true; break; }
            if (!dup) g_probePages.push_back(a);
        }
    }
    for (size_t i = 0; i < g_probePages.size(); ++i) {
        MEMORY_BASIC_INFORMATION mbi;
        DWORD prot = PAGE_READWRITE;
        if (VirtualQuery((LPCVOID)g_probePages[i], &mbi, sizeof(mbi)))
            prot = mbi.Protect & ~(DWORD)PAGE_GUARD;
        g_probeProt.push_back(prot);
    }
    if (!g_probeVeh) g_probeVeh = AddVectoredExceptionHandler(1, ProbeHandler);
    ArmProbePages();
    Log("probe armed: %zu table range(s), %zu row(s), %zu page(s), ProbeAll=%d",
        g_probeRanges.size(), g_probeRows.size(), g_probePages.size(), (int)g_cfg.probeAll);
    return (int)g_probePages.size();
}

// --------------------------------------------------------------- worker
DWORD WINAPI Worker(LPVOID) {
    std::vector<TableState> tables;

    for (int attempt = 0; attempt < 600; ++attempt) {
        std::vector<uint64_t> found = ScanForTables();
        if (!found.empty()) {
            tables.clear();
            for (uint64_t t : found) {
                TableState st;
                st.addr = t;
                tables.push_back(st);
            }
            break;
        }
        Sleep(1000);
    }
    Log("param tables located: %zu", tables.size());
    if (tables.empty()) Log("WARNING: %s not found (params not loaded?)", kParamName);

    if (g_cfg.probe) {
        const int pages = PrepareProbe(tables);
        Log("probe mode: writing NOTHING; re-arming every %d ms", g_cfg.probeRearmMs);
        int wcmDumps = 0;
        for (int tick = 0;; ++tick) {
            Sleep((DWORD)g_cfg.probeRearmMs);
            if (pages > 0 && g_probeStepPageAddr == 0) ArmProbePages();
            // the engine keeps several copies of a param table around and only one of
            // them is the live one; re-scan often at first and arm every copy we find
            if (tick == 30 || tick == 60 || tick == 100 || tick == 150 || tick == 200 ||
                tick == 300 || tick == 400 || tick == 600 || tick == 1200) {
                std::vector<uint64_t> found = ScanForTables();
                std::vector<TableState> extra;
                for (uint64_t t : found) {
                    bool have = false;
                    for (TableState& st : tables) if (st.addr == t) { have = true; break; }
                    if (!have) { TableState st; st.addr = t; extra.push_back(st); }
                }
                Log("probe: rescan found %zu table(s), %zu new", found.size(), extra.size());
                if (!extra.empty()) { PrepareProbe(extra); for (TableState& st : extra) tables.push_back(st); }
            }
            // player identification that needs no gameplay input
            if (tick == 200 || tick == 600 || tick == 1500) ProbeScanPlayerModel();
            // player pointer graph, no gameplay needed
            if (g_cfg.worldChrManOffset && wcmDumps < 3 && (tick % 50) == 49) {
                ProbeDumpWorldChrMan();
                ++wcmDumps;
            }
        }
    }

    for (;;) {
        LoadConfig();
        int live = 0, rowsTotal = 0, writes = 0;
        for (TableState& st : tables) {
            const int n = ApplyTable(st, &writes);
            if (n > 0) { ++live; rowsTotal += n; }
            else { st.valid = false; }
        }
        if (writes > 0) {
            Log("applied %d field write(s) over %d row(s) in %d table(s)",
                writes, rowsTotal, live);
        }
        if (!tables.empty() && live == 0) {
            Log("tables went stale, rescanning");
            std::vector<uint64_t> found = ScanForTables();
            tables.clear();
            for (uint64_t t : found) {
                TableState st;
                st.addr = t;
                tables.push_back(st);
            }
            Log("rescan found %zu", tables.size());
        }
        Sleep((DWORD)g_cfg.intervalMs);
    }
    return 0;
}

} // namespace

BOOL APIENTRY DllMain(HMODULE mod, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(mod);
        g_exeBase = (uint64_t)GetModuleHandleW(nullptr);
        InitializeCriticalSection(&g_logLock);
        g_logLockReady = true;
        const std::wstring dir = ModuleDir(mod);
        g_iniPath = dir + L"\\HideSheathedLeft.ini";
        g_logPath = dir + L"\\HideSheathedLeft.log";
        LoadConfig();
        Log("--- HideSheathedLeft loaded (pid %lu) ---", GetCurrentProcessId());
        if (HANDLE th = CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr)) {
            CloseHandle(th);
        }
    }
    return TRUE;
}
