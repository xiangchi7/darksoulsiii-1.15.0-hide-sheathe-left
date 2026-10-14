// ============================================================================
//  xinput1_3.dll  --  mod loader shell + HideSheathedLeft host
// ----------------------------------------------------------------------------
//  DarkSoulsIII.exe imports XINPUT1_3.dll by ORDINAL (2 = XInputGetState,
//  3 = XInputSetState -- verified with `dumpbin /imports`), which is why this
//  slot is the earliest automatic entry point into the process: our DllMain
//  runs while the game's imports are being resolved, BEFORE its entry point.
//
//  What this DLL does, in order:
//    1. mirrors the COMPLETE export table of the real system DLL (ordinals
//       1..8, same names) and forwards every call to
//       %SystemRoot%\System32\xinput1_3.dll -- loaded by absolute path so we
//       can never recurse into ourselves.  Gamepad, rumble, Steam overlay and
//       any other module importing XInput (by name or ordinal) keep working.
//    2. optionally loads HideSheathedLeft.dll  ([loader] LoadCore=1)
//    3. loads any number of other mod DLLs listed in [loader] ExtraMods, so
//       several DLL mods can share this one import slot instead of fighting
//       over the file name.
//
//  Everything is logged to xinput1_3_proxy.log next to this DLL.
//
//  Config (HideSheathedLeft.ini next to this file):
//      [loader]
//      LoadCore=1
//      ExtraMods=dkp_loader.dll, SomeOtherMod.dll
//      ExtraModsDelayMs=0        ; 0 = load immediately (earliest possible)
// ============================================================================

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace {

HMODULE      g_real = nullptr;
std::wstring g_dir;
std::wstring g_ini;

void LogLine(const wchar_t* fmt, ...) {
    const std::wstring path = g_dir + L"\\xinput1_3_proxy.log";
    if (FILE* f = _wfopen(path.c_str(), L"a, ccs=UTF-8")) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fwprintf(f, L"[%02d:%02d:%02d] ", st.wHour, st.wMinute, st.wSecond);
        va_list ap;
        va_start(ap, fmt);
        vfwprintf(f, fmt, ap);
        va_end(ap);
        fwprintf(f, L"\n");
        fclose(f);
    }
}

std::wstring SelfDir(HMODULE mod) {
    wchar_t path[MAX_PATH] = {0};
    GetModuleFileNameW(mod, path, MAX_PATH);
    std::wstring s(path);
    const size_t p = s.find_last_of(L"\\/");
    return (p == std::wstring::npos) ? std::wstring(L".") : s.substr(0, p);
}

void LoadReal() {
    if (g_real) return;
    wchar_t sys[MAX_PATH] = {0};
    GetSystemDirectoryW(sys, MAX_PATH);
    const std::wstring real = std::wstring(sys) + L"\\xinput1_3.dll";
    g_real = LoadLibraryW(real.c_str());
}

FARPROC Real(const char* name) {
    if (!g_real) LoadReal();
    return g_real ? GetProcAddress(g_real, name) : nullptr;
}

std::wstring Trim(const std::wstring& s) {
    const size_t b = s.find_first_not_of(L" \t\r\n");
    if (b == std::wstring::npos) return L"";
    const size_t e = s.find_last_not_of(L" \t\r\n");
    return s.substr(b, e - b + 1);
}

// "a.dll, b.dll;c.dll" -> individual entries
std::vector<std::wstring> SplitList(const std::wstring& s) {
    std::vector<std::wstring> out;
    std::wstring cur;
    for (wchar_t c : s) {
        if (c == L',' || c == L';' || c == L'\n' || c == L'\r') {
            const std::wstring t = Trim(cur);
            if (!t.empty()) out.push_back(t);
            cur.clear();
        } else {
            cur.push_back(c);
        }
    }
    const std::wstring t = Trim(cur);
    if (!t.empty()) out.push_back(t);
    return out;
}

std::wstring ResolvePath(const std::wstring& entry) {
    if (entry.find(L':') != std::wstring::npos || entry.rfind(L"\\\\", 0) == 0)
        return entry;                       // already absolute / UNC
    return g_dir + L"\\" + entry;
}

void LoadOne(const std::wstring& entry) {
    const std::wstring full = ResolvePath(entry);
    if (GetFileAttributesW(full.c_str()) == INVALID_FILE_ATTRIBUTES) {
        LogLine(L"  %s -- not present, skipped", entry.c_str());
        return;
    }
    HMODULE h = LoadLibraryW(full.c_str());
    LogLine(L"  %s -- %s (handle=0x%p)", entry.c_str(),
            h ? L"loaded" : L"FAILED", (void*)h);
}

void LoadExtraMods() {
    wchar_t buf[2048] = {0};
    GetPrivateProfileStringW(L"loader", L"ExtraMods", L"dkp_loader.dll",
                             buf, 2048, g_ini.c_str());
    const std::vector<std::wstring> entries = SplitList(buf);
    if (entries.empty()) {
        LogLine(L"extra mods: none configured");
        return;
    }
    LogLine(L"extra mods: %zu entr%s", entries.size(),
            entries.size() == 1 ? L"y" : L"ies");
    for (const std::wstring& e : entries) LoadOne(e);
}

DWORD WINAPI DelayedLoadWithSleep(LPVOID param) {
    Sleep((DWORD)(uintptr_t)param);
    LoadExtraMods();
    return 0;
}

void Boot(HMODULE mod) {
    const int loadCore = GetPrivateProfileIntW(L"loader", L"LoadCore", 1, g_ini.c_str());
    if (loadCore) {
        const std::wstring core = g_dir + L"\\HideSheathedLeft.dll";
        if (GetFileAttributesW(core.c_str()) == INVALID_FILE_ATTRIBUTES) {
            LogLine(L"core HideSheathedLeft.dll -- not present, skipped");
        } else {
            HMODULE h = LoadLibraryW(core.c_str());
            LogLine(L"core HideSheathedLeft.dll -- %s (handle=0x%p)",
                    h ? L"loaded" : L"FAILED", (void*)h);
        }
    } else {
        LogLine(L"core loading disabled by ini (LoadCore=0)");
    }

    const int delay = (int)GetPrivateProfileIntW(L"loader", L"ExtraModsDelayMs", 0, g_ini.c_str());
    if (delay > 0) {
        LogLine(L"extra mods will load in %d ms (background thread)", delay);
        if (HANDLE th = CreateThread(nullptr, 0, DelayedLoadWithSleep,
                                     (LPVOID)(uintptr_t)delay, 0, nullptr)) {
            CloseHandle(th);
        }
    } else {
        LoadExtraMods();
    }
}

// Generic forwarders: all XInput entry points take 1..3 scalar/pointer args
// and return DWORD (or void for XInputEnable), so plain casts are safe.
typedef DWORD(WINAPI* Fn2)(DWORD, void*);
typedef DWORD(WINAPI* Fn3)(DWORD, void*, void*);
typedef DWORD(WINAPI* Fn3d)(DWORD, DWORD, void*);
typedef void (WINAPI* FnVoid1)(BOOL);

} // namespace

extern "C" BOOL APIENTRY DllMain(HMODULE mod, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(mod);
        g_dir = SelfDir(mod);
        g_ini = g_dir + L"\\HideSheathedLeft.ini";
        LoadReal();
        LogLine(L"--- mod loader shell attached (pid %lu) ---", GetCurrentProcessId());
        Boot(mod);
    }
    return TRUE;
}

extern "C" BOOL WINAPI ProxyDllMainEntry(HMODULE, DWORD, LPVOID) { return TRUE; }

extern "C" DWORD WINAPI XInputGetState(DWORD index, void* state) {
    const FARPROC p = Real("XInputGetState");
    return p ? ((Fn2)p)(index, state) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputSetState(DWORD index, void* vibration) {
    const FARPROC p = Real("XInputSetState");
    return p ? ((Fn2)p)(index, vibration) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetCapabilities(DWORD index, DWORD flags, void* caps) {
    const FARPROC p = Real("XInputGetCapabilities");
    return p ? ((Fn3d)p)(index, flags, caps) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" void WINAPI XInputEnable(BOOL enable) {
    const FARPROC p = Real("XInputEnable");
    if (p) ((FnVoid1)p)(enable);
}

extern "C" DWORD WINAPI XInputGetDSoundAudioDeviceGuids(DWORD index, void* render, void* capture) {
    const FARPROC p = Real("XInputGetDSoundAudioDeviceGuids");
    return p ? ((Fn3)p)(index, render, capture) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetBatteryInformation(DWORD index, BYTE devType, void* info) {
    const FARPROC p = Real("XInputGetBatteryInformation");
    return p ? ((Fn3d)p)(index, (DWORD)devType, info) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetKeystroke(DWORD index, DWORD reserved, void* keystroke) {
    const FARPROC p = Real("XInputGetKeystroke");
    return p ? ((Fn3d)p)(index, reserved, keystroke) : ERROR_DEVICE_NOT_CONNECTED;
}
