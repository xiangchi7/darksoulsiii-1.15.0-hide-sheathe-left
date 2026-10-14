// scan-test.cpp -- measures what HideSheathedLeft's table scan does to the working
// set of the process it is loaded into (the number Task Manager shows for
// DarkSoulsIII.exe), without having to launch the game.
//
//   cl /nologo /O2 /EHsc /std:c++17 scan-test.cpp /Fe:scan-test.exe
//
//   scan-test.exe <HideSheathedLeft.dll> [big-file-to-map]
//
//   scan-test.exe dist\HideSheathedLeft.dll "D:\Steam\steamapps\common\DARK SOULS III\Game\Data1.bdt"
//
// It builds a synthetic stand-in for Dark Souls III's memory layout:
//   * a 3 GB private pool that is committed up front but only sparsely touched
//     (DS3 commits its resource pools immediately -- ~8 GB is normal -- and keeps
//     only a fraction of those pages resident), and
//   * a read-only view of a large file that is never touched (the DS3-style
//     memory-mapped archive / loose chr file case).
// Then it loads the mod under test and prints the working set for 12 seconds.
//
// 1.0.1 in this harness: 99 MB -> 4010 MB.  1.0.2: 99 MB -> 99 MB (peak 103 MB).
// Full data: docs\MEMORY-FIX-1.0.2.md.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <cstdio>

#pragma comment(lib, "psapi.lib")

static unsigned long long WsMB() {
    PROCESS_MEMORY_COUNTERS pmc = {0};
    if (!K32GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) return 0;
    return (unsigned long long)(pmc.WorkingSetSize >> 20);
}

static unsigned long long PeakMB() {
    PROCESS_MEMORY_COUNTERS pmc = {0};
    if (!K32GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) return 0;
    return (unsigned long long)(pmc.PeakWorkingSetSize >> 20);
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 2) {
        wprintf(L"usage: scan-test.exe <HideSheathedLeft.dll> [big-file-to-map]\n");
        return 2;
    }

    const size_t kPool = 3ull << 30;   // 3 GB committed, sparsely touched
    unsigned char* pool = (unsigned char*)VirtualAlloc(nullptr, kPool,
                                                       MEM_RESERVE | MEM_COMMIT,
                                                       PAGE_READWRITE);
    if (!pool) {
        wprintf(L"VirtualAlloc(3 GB) failed (%lu)\n", GetLastError());
        return 3;
    }
    for (size_t off = 0; off < kPool; off += 128 * 1024) pool[off] = 1;   // ~1/32 of the pages

    void* view = nullptr;
    HANDLE hMap = nullptr, hFile = nullptr;
    if (argc > 2) {
        hFile = CreateFileW(argv[2], GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                            nullptr, OPEN_EXISTING, 0, nullptr);
        if (hFile != INVALID_HANDLE_VALUE) {
            hMap = CreateFileMappingW(hFile, nullptr, PAGE_READONLY, 0, 0, nullptr);
            if (hMap) view = MapViewOfFile(hMap, FILE_MAP_READ, 0, 0, 0);
        }
    }

    wprintf(L"pool: 3 GB committed, sparsely touched; mapped file: %s\n",
            view ? L"mapped, never touched" : L"none");
    wprintf(L"working set before load : %llu MB (peak %llu MB)\n", WsMB(), PeakMB());

    HMODULE h = LoadLibraryW(argv[1]);
    if (!h) {
        wprintf(L"LoadLibrary failed (%lu)\n", GetLastError());
        return 4;
    }

    for (int i = 1; i <= 12; ++i) {
        Sleep(1000);
        wprintf(L"  t+%2ds  working set: %llu MB (peak %llu MB)\n", i, WsMB(), PeakMB());
    }
    wprintf(L"done (mod still loaded)\n");
    return 0;
}
