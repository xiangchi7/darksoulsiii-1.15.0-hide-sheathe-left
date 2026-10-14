# HideSheathedLeft — Dark Souls III 1.15.0

While you two-hand one hand's weapon, the **other hand's sheathed model is no longer drawn on your
back**. The behaviour is symmetric: two-hand the right weapon and the left item disappears; two-hand
the left weapon and the right item disappears. Works for anything hand-equippable: weapons, shields,
catalysts, bows, staves.

> Dark Souls III **1.15.0** (Steam, 64-bit). Local memory + model changes only. Online play has
> a server-side save sanity check — use it offline.

---

## What it does

| Situation | Vanilla | With this mod |
|---|---|---|
| Right-hand weapon **two-handed**, left hand occupied | left item hangs on your back | left item is **not drawn** |
| **Left-hand** weapon two-handed, right hand occupied | right item hangs on your back | right item is **not drawn** |
| The stowed item **in use** (blocking / swinging) | drawn normally | **drawn normally** (unaffected) |
| **Paired weapon** held one-handed (either hand) | spare model sits on the body | spare model **not drawn** (`PairedFields` can hide only the blade and keep the scabbard) |

**How:** the `leftHang_0..3` / `rightHang_0..3` and `right_1..3` / `left_1..3` fields of
`WepAbsorpPosParam` are pointed at a **parking dummy** (id `382`, with `383` as a spare) that sits
**1000 m below the character**. The model is still attached, just far outside the world — so nothing
is drawn, and because the dummy is a *real* dummy (not an invalid poly like `-1` in 1.0.0) the engine
builds a valid matrix, which removes the 1.0.0 **black triangles / full-screen flicker**.

The parking dummies are appended to **every character model** (`chr\*.chrbnd.dcx`), so no
character — player or NPC — can ever resolve a missing dummy.

---

## Requirements

* Dark Souls III 1.15.0 (Steam).
* A **loose-file setup** (`Game\chr\*.chrbnd.dcx` exists — the normal state after unpacking with
  UXM, which model mods require). The bundled patcher edits those files in place.
* Windows PowerShell (built in). .NET 8/10 runtime is only needed if you rebuild the tools.

---

## Install

> **Which download?** `HideSheathedLeft-<version>-full.zip` is the install package (payload in
> `files\`, plus the screenshot evidence and the reference dumps). `HideSheathedLeft-<version>.zip`
> is the same mod in repository layout (source, research scripts, validator, full documentation) --
> `install.cmd` works there too since 1.0.3; it patches all 165 character models with
> `tools\ds3tae.exe` instead of shipping a pre-patched player model.

1. Close the game.
2. Double-click **`install.cmd`** (or run `powershell -ExecutionPolicy Bypass -File install.ps1`).

It copies the payload into the game folder and then appends dummy 382/383 to every
`chr\*.chrbnd.dcx` (each file is verified before writing; files that already have the dummies are
skipped). Manual, step-by-step install: [`docs/MANUAL-INSTALL.txt`](docs/MANUAL-INSTALL.txt).

Check the state at any time:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Status
```

### Uninstall

Double-click **`restore.cmd`** (or `restore.ps1`). It replays
`<game>\.hsleft-manifest.json`, which `install.ps1` wrote:

* every file the installer overwrote is copied back from `<game>\.hsleft-backup\<same relative
  path>` and verified against the SHA-256 that was recorded before the install, so the game
  returns to its **exact pre-install bytes**
* every file the installer created (the DLL, the ini, and `chr\c0000.chrbnd.dcx` when you had no
  loose `chr\` at all) is deleted again
* every directory the installer created is removed when it ends up empty
* finally `tools\ds3tae.exe verify` scans `chr\` and reports which models still carry dummy
  382/383, so "nothing is left behind" is evidence, not a promise

```powershell
powershell -ExecutionPolicy Bypass -File restore.ps1 -DryRun       # report only, change nothing
powershell -ExecutionPolicy Bypass -File restore.ps1 -AllowLegacy  # 1.0.4-and-older installations
powershell -ExecutionPolicy Bypass -File restore.ps1 -KeepBackups  # keep backups + manifest
```

If a file is **not** the one the installer put there any more (you replaced it, or another mod
did), the restore stops and tells you instead of overwriting someone else's work; `-Force`
finishes it.  When that happens the manifest and the backups are kept so the retry is possible.

**Installations made by 1.0.4 or older have no manifest** and no native copies of the character
models.  Their `tools\ds3tae.exe` cannot even strip them: the packaged binary predates the
`stripdir` sub-command, so it answers with a usage line and exit code 2 (that is why the old
`restore.ps1` "finished" without undoing anything).  Use the `tools\` folder of this version
instead and run `restore.ps1 -AllowLegacy`.  A structural strip is *not* byte-identical: the tool
removes the dummies and proves that everything else (bones, materials, meshes, buffer layouts) is
untouched, but re-serialising the bundle and re-compressing the DCX always produces a slightly
different file.  A fresh install now avoids that entirely by keeping the originals.

Backups cost disk space: the `.hsleft-backup\chr\` copies are the same size as the models
(roughly 340 MB for a full 165-model `chr\`).  `install.ps1` prints the size before it starts.
They are deleted by `restore.ps1` and are only there so the uninstall can be exact.

---

## Configuration

`HideSheathedLeft.ini` (saved changes apply within a second, no restart needed):

| Key | Default | Meaning |
|---|---|---|
| `HideLeftHang` | `1` | hide the sheathed left-hand item (reached by two-handing the **right** weapon) |
| `HideRightHang` | `1` | mirror image: hide the sheathed right-hand item (reached by two-handing the **left** weapon) |
| `HideBothPaired` | `1` | hide the spare model of a one-handed paired weapon, **both hands** |
| `PairedFields` | `1,2,3` | which models of a paired weapon to hide: `1` = blade only (keeps the scabbard), `none` = leave paired weapons alone |
| `HidePoly` | `382` | parking dummy id (`383` spare, `-1` reproduces the 1.0.0 artefacts) |
| `IntervalSeconds` | `1` | how often the parameter values are re-asserted |
| `Rescan` | `1` | `0` = stop the periodic address-space re-scan (see "Performance" below) |
| `ScanMapped` | `0` | `1` = also consider MEM_MAPPED regions (diagnostic) |
| `Probe` | `0` | `1` = observation only (writes nothing, logs to `HideSheathedLeft.log`) |
| `ExtraMods` | *(empty)* | must stay empty — loading additional DLLs on 1.15.0 crashes the game |

Setting `HideLeftHang=0` restores vanilla for the right-hand two-hand stance only; setting
`HideRightHang=0` does the same for the left-hand two-hand stance. The older key
`HidePairedOffhand` is still read when `HideBothPaired` is absent (it only ever covered the
right hand).

---

## Performance

The parameter writes are the cheap part: they only happen when a value actually differs, so steady
state is a handful of memory reads per second. The expensive part is finding the parameter table in
the first place — the mod walks the process's memory regions and copies their **resident** pages
looking for the table name. That runs once at start-up, and again only when the addresses it holds
go stale (`Rescan=1`, the default, keeps the effect self-healing).

* 1.0.1 read **non-resident** pages as well. That faults paged-out data back into RAM; DS3 commits
  its resource pools up front, so the game's working set jumped by ~4 GB (measured 6007 MB vs
  vanilla 1634 MB) and the stutter was much worse. 1.0.2 made the scan resident-only and every
  version since, including this one, is resident-only.
* If you see stutter, set **`Rescan=0`**. Then no further address-space pass runs after the
  start-up scan and the mod is reduced to those few reads per second. Trade-off: if the engine
  rebuilds the table mid-session, the effect can stay off until the next launch.
* `HideSheathedLeft.log` records what each pass cost, e.g.
  `scan: 4 table(s); read 0 MB resident, left 7615 MB untouched of 7619 MB seen`. If stutter
  persists with `Rescan=0` and no scan lines appear in the log, the mod is not what is costing you
  frames — please report the log either way.

---

## Known limitations

* **NPCs hide the item too.** The parameter table is shared between the player and NPCs, and
  the mod makes the parking dummy valid for every character model, so an NPC in the same stance
  simply does not draw its sheathed left item instead of producing artefacts. Making it
  player-only requires patching the engine's attach resolver — see
  [`docs/TECHNICAL-NOTES.md`](docs/TECHNICAL-NOTES.md) for the code sites already identified
  (`exe+0xE31690` selector, single call site `exe+0xE35125`, accessor `exe+0xE350D0`).
* **Rare "silent no-op".** The engine keeps several copies of the parameter table in memory and
  the mod can only rewrite the ones it finds, so occasionally the copy the engine actually reads
  is missed: the item stays on your back (no artefacts) until the next launch. Root cause: the
  engine **caches** the resolved attach values per character and rarely re-reads the table.
* **1.0.4 and earlier cannot uninstall.** Their packaged `tools\ds3tae.exe` has no `stripdir`, and
  their `restore.ps1` reported success while leaving every character model patched. Use this
  version's scripts and `tools\`; see the Uninstall section above.
* After another mod replaces files in `chr\`, run `install.cmd` (or
  `tools\patch-character-models.ps1`) again — already-patched files are skipped.

---

## Build from source

Needs Visual Studio Build Tools (MSVC, x64) and the .NET SDK:

```powershell
# mod core + loader shell -> dist\
powershell -ExecutionPolicy Bypass -File src\build.ps1

# the model patch / validation tool -> validator\bin\Release\net10.0\ds3tae.exe
dotnet build validator\validator.csproj -c Release
```

* `src\HideSheathedLeft.cpp` — the mod core (locates the parameter tables, writes the parking
  dummy, optional diagnostic probe)
* `src\xinput1_3_proxy.cpp` / `.def` — loader shell (mirrors the XInput 1..8 exports)
* `validator\Main.cs` — the `ds3tae` tool: `parkdir`, `stripdir`, `scanid`, `flverdiff`,
  `dummies`, `inspect`, `disasm`-helpers …

---

## Repository layout

```
HideSheathedLeft.dll      mod core (prebuilt)
HideSheathedLeft.ini      configuration
xinput1_3.dll             loader shell (forwards the system XInput)
install.cmd / .ps1        install (payload + character-model patch)
restore.cmd / .ps1        uninstall
tools\ds3tae.exe          model patch / validation tool
tools\maintainer\         scripts used to publish releases through the GitHub API
docs\                     manual install, technical notes, TAE plan, animation id maps, data dumps
docs\zh-CN\               the same documentation in Chinese
research\runtime\         live-process probing helpers (Python)
research\static\          offline FLVER / TAE / EXE analysis helpers
research\analysis\        planning and document-sync scripts
research\imaging\         screenshot comparison helpers
src\ validator\           sources
```

## Version lineage

| Tag | What |
|---|---|
| `v1.0.0` | first approach: wrote an invalid dummy poly (`-1`). Worked, but the retail engine built a degenerate matrix from it → black triangles + full-screen flicker. Kept as history (and as a way to reproduce the bug for comparison). |
| `v1.0.1` | parks the model at a real dummy 1000 m below the character and appends that dummy to every character model. No artefacts — but while looking for the parameter tables it read every committed page of the process, which made the game appear to use ~4 GB more RAM (fixed in 1.0.2). |
| `v1.0.2` | identical behaviour, but the table search is resident-only, so the game's memory footprint is indistinguishable from vanilla (peak working set 1624 MB vs vanilla 1634 MB; 1.0.1 was 6007 MB). |
| `v1.0.3` | packaging: `install.cmd` works in the plain (repository) zip too. |
| `v1.0.4` | symmetric effect: the sheathed right-hand item is hidden too (`HideRightHang`), paired spares hidden in both hands (`HideBothPaired`). |
| `v1.0.5` | **uninstall fixed** (byte-exact manifest + rebuilt `ds3tae.exe`; 1.0.4 could not uninstall at all), `Rescan` documented as the performance switch, `build.ps1` fixed. Mod behaviour unchanged. |

## Notes

* This repository ships **no game assets**: `tools\ds3tae.exe` only appends two dummies to
  **your own** `chr\*.chrbnd.dcx` files (and verifies that everything else stays byte-identical).
* `install.ps1` keeps a byte-exact copy of every file it is about to overwrite in
  `<game>\.hsleft-backup\` and records all of it in `<game>\.hsleft-manifest.json`, so
  `restore.ps1` can put the originals back exactly.  `tools\ds3tae.exe stripdir` remains as the
  structural fallback for installations that have no manifest (`restore.ps1 -AllowLegacy`).
* Round-trip proof: `powershell -ExecutionPolicy Bypass -File tests\roundtrip.ps1` builds a
  scratch game folder, installs, restores and fails unless every pre-existing file is
  byte-identical and nothing is left over.
* Memory: the table scan only reads pages the OS currently holds resident, so it cannot pull the
  game's paged-out resource pools back into RAM. `HideSheathedLeft.log` prints what each scan cost
  — see `docs\MEMORY-FIX-1.0.2.md`.
* Only one `xinput1_3.dll` can live in the game folder: if another mod (e.g. a key-prompt mod)
  already owns that slot, the installer renames it to `xinput1_3.dll.dkp-off` and keeps it.
  The two mods cannot be active at the same time.

## License

MIT — see [`LICENSE`](LICENSE). Not affiliated with FromSoftware or Bandai Namco; single-player,
offline use only.
