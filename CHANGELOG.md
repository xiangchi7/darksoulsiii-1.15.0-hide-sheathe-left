# Changelog

## 1.0.5

**The uninstall did not work at all, and reports of frame drops have to be taken seriously.**
This release fixes the uninstall, makes the bundled tool actually work, rebuilds the mod core with
the same behaviour, and documents the one switch that controls how much CPU the mod uses while you
play.

### Fixed
* **The uninstall did not restore the game to its pre-install state.** Three separate reasons:
  1. `tools\ds3tae.exe` **as shipped in v1.0.4 and earlier** has no `stripdir`/`parkdir`/`scanid`
     at all: the packaged binary predates those sub-commands, so it answers
     `usage: validate <file>... | ...` and exits 2 (verified against
     `publish-1.0.4\...\tools\ds3tae.exe`, 38,912-byte `ds3tae.dll`). `restore.ps1` only printed a
     warning and carried on, then reported "Restore finished", so **every character model stayed
     patched and the user had no way to tell**. The tool is rebuilt from source and re-synced into
     `tools\` (50,688-byte `ds3tae.dll`); running it with no arguments now lists its sub-commands,
     which is the one-line check for this class of problem.
  2. `stripdir` only ever touched the **first** FLVER of a bundle (as did `parkdir` and the
     post-write check), and its `DRYRUN` flag was read from the wrong argument index.
  3. Even a correct strip is not byte-exact: re-serialising the BND4 and re-compressing the DCX
     produces a different file (measured 43,792 -> 47,220 bytes for a model whose dummies were
     removed again, identical decompressed payload). Every character model the installer touched
     was therefore permanently different from the original, and `chr\c0000.chrbnd.dcx` was left
     behind on a game that had no loose `chr\` folder before.
* **`src\build.ps1` could not build at all.** It joined `$PSScriptRoot` + `src` while itself living
  in `src\`, so every compile failed with `C1083: cannot open source file ...\src\src\...`, and it
  looked for `HideSheathedLeft.ini` inside `src\`. It now resolves the repository root, writes to
  `<repo>\dist\` as documented, and works when invoked as `src\build.ps1` (as the README says).
  This is why the shipped mod binaries had not been rebuilt since 1.0.4 even though the source
  carries the newer code.

### Changed
* **The mod core is rebuilt with the same behaviour.** The only source change is the reported
  version (`kVersion` `1.0.4` -> `1.0.5`, visible in `HideSheathedLeft.log`). No timing, scanning or
  patching logic was altered, because the frame-drop report below could not be reproduced here in a
  controlled way -- see "Known issues".
* `HideSheathedLeft.ini`: the `Rescan` switch is now documented as what it is -- **the one setting
  that decides how much work the mod does in the background**. `Rescan=1` (default) keeps the
  self-healing pass that re-finds the parameter tables if the engine rebuilds them; `Rescan=0`
  stops those extra full passes, so after start-up the worker only reads the rows it already holds.
  If you see frame-time spikes while playing, this is the switch to try first.
* `tools\patch-character-models.ps1` gained `-Only <names>` (used by the installer so a re-install
  never touches a model it already patched) and no longer fails on a game folder without a loose
  `chr\` — it reports that there is nothing to patch and exits 0.
* `install.ps1 -Force` (and the existing `restore.ps1 -Force`) skip the "close the game first"
  check, for scripted round trips only.
* `install.ps1 -Status` prints the manifest and works without the bundled tool (the `scanid`
  call used to pass its arguments in the wrong order and needed the rebuilt binary anyway).
* `ds3tae.exe` with no arguments now prints the full sub-command list instead of a four-command
  usage line, and `scanid`/`verify` exit 0 for a conclusive scan ("hits found" is a result, not a
  failure); `install.ps1` therefore always exits 0 unless it really failed.
* README, `docs\MANUAL-INSTALL.txt`, `docs\TECHNICAL-NOTES.md` and their `zh-CN` counterparts: the
  uninstall/restore sections were rewritten for the manifest workflow.

### Added
* **`install.ps1` records everything it does.** Before a file is overwritten it is copied byte for
  byte to `<game>\.hsleft-backup\<same relative path>`, and `<game>\.hsleft-manifest.json` records,
  per file, whether it existed, its SHA-256 before and after the install, its size and its backup
  path, plus every directory the installer created. `chr\*.chrbnd.dcx` files that already carried
  382/383 (an earlier install, another model mod) are left alone and reported, because no native
  copy of them exists. A re-install over a previous one keeps the *first* install's originals.
* **`restore.ps1` replays that manifest**: originals come back byte-exact and are verified against
  the recorded hash, installer-created files (DLL, ini, `chr\c0000.chrbnd.dcx`) are deleted again,
  installer-created directories (including an empty `chr\`) are removed. If a file is no longer the
  one the installer put there, the restore stops and says so (exit 1) instead of overwriting
  someone else's work, keeps the manifest and backups for a retry, and `-Force` finishes the job.
* `ds3tae verify <root> [filter] [ids]` — the end-of-restore proof: it lists every file that still
  carries the parking dummies and states that a model which had them before the install keeping
  them is the pre-install state, not a leftover.
* `restore.ps1 -AllowLegacy` — the explicit opt-in for installations made by 1.0.4 or older (no
  manifest). Without it, `restore.ps1` refuses to guess and changes nothing.
* `tests\roundtrip.ps1` — installs into a scratch game folder, restores, and fails unless every
  pre-existing file is byte-identical and nothing is left over; also covers a double install, the
  "file replaced after the install" safety catch and `-Force`.

### Known issues
* **Frame-time spikes have been reported with this mod running, and the cause is not established.**
  What is known: the mod's parameter writes are cheap and only happen when a value differs; the
  expensive work is the address-space scan, which runs once at start-up and again whenever the held
  table addresses go stale (`Rescan=1`, the default). That pass walks the process's regions and
  copies their resident pages to look for the parameter table name, so it scales with how much of
  your RAM is resident; the log prints what each pass cost, e.g.
  `scan: 4 table(s); read 0 MB resident, left 7615 MB untouched of 7619 MB seen`. 1.0.1 read
  non-resident pages as well, which dragged the whole resource pool into physical memory (~4 GB extra
  in the game's working set) and made the stutter far worse; 1.0.2 fixed that and every version since
  is resident-only. **If you see stutter, set `Rescan=0`** and check `HideSheathedLeft.log`: with no
  "rescan" lines after start-up, the mod is reduced to a few memory reads per second. Please report
  what the log says either way -- this is the one open performance question.
* The parameter table is shared by the player and NPCs, so an NPC in the same stance hides its
  sheathed item too (no artefacts: the parking dummy is valid for every character model).
* The engine keeps several copies of the parameter table in memory and caches resolved attach
  values, so the effect can occasionally stay off until the next launch ("silent no-op").
* Online play has a server-side save check — use it offline.

### Notes
* The uninstall of **1.0.4 and earlier is broken** (see "Fixed" above): those packages cannot strip
  the character models even if you run their `restore.ps1`, and their `stripdir` is a no-op. If you
  installed with an older package and want the models back to their original bytes, delete the loose
  `chr\*.chrbnd.dcx` and re-extract them (UXM), or use this version's `tools\` with
  `restore.ps1 -AllowLegacy` for a structural (not byte-identical) undo.
* **Why the version number moved even though the mod behaves the same.** The shipped binaries had
  not been rebuilt since 1.0.4 while the working tree carried newer source, which is exactly the
  failure mode that produced the broken tool in the 1.0.4 package. `HideSheathedLeft.dll` and
  `xinput1_3.dll` in this package are now built from this repository's sources
  (`src\build.ps1`, MSVC x64), and `HideSheathedLeft.log` reports `1.0.5` so a package and its
  binary can be matched. Verify with
  `findstr /c:"1.0.5" HideSheathedLeft.dll` (the string is stored narrow) or by reading the log.
* Upgrading from 1.0.4 needs `HideSheathedLeft.dll` **and** the `tools\` / scripts from this
  package. The character-model patch does not have to be re-run if it is already applied.
* Round-trip proof for this package: `powershell -ExecutionPolicy Bypass -File tests\roundtrip.ps1`
  ends with `ROUND TRIP OK`, and an install -> restore from the extracted `-full` zip leaves the
  test game folder with exactly the files it started with.

## 1.0.4

Makes the effect **symmetric**: two-handing the *left*-hand weapon now hides the right-hand item,
exactly mirroring what two-handing the right-hand weapon has always done to the left-hand item.

### Added
* **`HideRightHang`** (default `1`) — hide the model of the sheathed **right**-hand item. The engine
  reaches that state by two-handing the left-hand weapon, where the right weapon/shield would
  otherwise be drawn on the back. Field offsets `0x0C/0x16/0x20/0x2A` (`rightHang_0..3`), the exact
  mirrors of the `leftHang_*` group (`0x0A/0x14/0x1E/0x28`).
* **`HideBothPaired`** (default `1`) — the paired-weapon spare models are now hidden for **both**
  hands: `left_1..3` (`0x10/0x1A/0x24`) in addition to the existing `right_1..3`
  (`0x0E/0x18/0x22`). `PairedFields` selects which model indices to park and applies to both hands.
* The field table is now described by an explicit per-field kind
  (`leftHang` / `rightHang` / `pairedR` / `pairedL`) instead of a single boolean, so the left-hand
  and right-hand paths cannot drift apart.

### Changed
* `HidePairedOffhand` is superseded by `HideBothPaired`; the old key is still honoured when
  `HideBothPaired` is absent, so an existing ini keeps working (it only ever covered the right hand).
* The start-up config line now reports
  `HideLeftHang=… HideRightHang=… HideBothPaired=… PairedFields=R…/L…`.

### Compatibility
* Same mechanism, same parking dummy (`382`/`383`), same model patch — **no new asset requirement**.
  A 1.0.2/1.0.3 installation only needs the new `HideSheathedLeft.dll` (and optionally the ini).
* Field count per row goes from 7 to 14, so the first pass after start-up writes roughly twice as
  many values once (`91 rows x 4 tables x 14 fields`); steady state is unchanged, since values are
  still only written when they actually differ.

## 1.0.3

Packaging fix: `install.cmd` / `install.ps1` now work in the plain (repository) zip as well, so
both release assets install the same way. The mod core is unchanged -- only the version it logs.

### Fixed
* **`missing kit file` when installing from `HideSheathedLeft-<version>.zip`.** The installer only
  looked for the payload in `files\`, which exists in the `-full` package but not in the plain
  (repository-layout) zip. It now falls back to the script directory, so `install.cmd` is a real
  one-click install in both packages. The player model (`files\c0000.chrbnd.dcx`) stays optional:
  when it is absent, the bundled `tools\ds3tae.exe parkdir` patches every `chr\*.chrbnd.dcx`,
  the player's model included (same result, verified).

### Changed
* README "Install" now spells out which download is which: `-full.zip` = install package (payload
  + evidence + reference), plain `.zip` = the same mod in repository layout (source, research
  scripts, validator, full documentation).
* `tools\maintainer\publish-1.0.2.ps1` -> `tools\maintainer\publish-release.ps1`; it always took a
  `-Version` argument, the name no longer claims a single release.
* `HideSheathedLeft.dll` is functionally identical to 1.0.2 (the search is still resident-only);
  only the version it writes to `HideSheathedLeft.log` changed, so an existing 1.0.2 installation
  does not have to replace anything.

## 1.0.2

Fixes the memory regression of 1.0.1: while looking for the parameter tables the mod read every
committed page of the process, which dragged the game's whole (mostly paged-out) resource pool
back into physical RAM. Behaviour is unchanged — same tables, same writes, same result.

### Fixed
* **The game using ~4 GB more RAM.** Windows had paged out most of DS3's pre-committed resource
  pools (~8 GB committed, ~1.6 GB resident); reading a paged-out page faults it back into physical
  memory, and reading `MEM_MAPPED` regions pulled mapped files in as well, so the scan made the
  whole pool resident at once. Measured with the same launch procedure, sampled every 2 s for
  100 s: 1.0.1 peaked at **6007 MB**, vanilla at **1634 MB**, 1.0.2 at **1624 MB**.
* The resident-only mitigation of the 1.0.1 development builds never took effect: every scan that
  failed to find the table fell back to a full read of private **and** mapped memory.

### Changed
* The table search is resident-only: `QueryWorkingSetEx` decides per page and only maximal runs of
  resident pages are copied. Pages the OS does not currently hold are skipped, never read.
* All full-read fallbacks are gone. If the table is not resident yet, the engine has not loaded it
  yet, so the worker waits one second and retries (600 attempts = 10 minutes).
* `ScanMapped=1` now only widens which regions are considered; their pages are still read
  resident-only, so the switch can no longer inflate the working set.
* The log now records the build version and what every scan cost, e.g. `scan: 4 table(s); read 0 MB
  resident, left 7615 MB untouched of 7619 MB seen; working set 1420 MB (peak 1520 MB)`.
* `docs\TECHNICAL-NOTES.md` gained section 6 (locating the tables without inflating the working
  set) and `HideSheathedLeft.ini` documents the scan policy.

### Added
* `docs\MEMORY-FIX-1.0.2.md` (+ `docs\zh-CN\MEMORY-FIX-1.0.2.zh-CN.md`): the mechanism, the raw
  measurements and how to confirm the fix from `HideSheathedLeft.log`.
* `research\runtime\scan-test.cpp` + `research\runtime\ram-ab.ps1`: the harnesses used to measure it
  (a synthetic stand-in for DS3's memory layout, and the in-game A/B/A/B run).

### Notes
* Upgrading from 1.0.1 only needs `HideSheathedLeft.dll` (plus the ini for the new documentation);
  the character-model patch does **not** have to be re-run.
* The mod's own footprint is a few MB: a 4 MB scan buffer that is reused per pass plus the table
  snapshot (a few KB per table). Interleaved on/off A/B/A/B in game measured +2.5 MB steady-state
  working set — below the run-to-run spread.

## 1.0.1

Fixes the fatal rendering problem of 1.0.0 and turns the "parking dummy" into a form that is safe
for every character model.

### Fixed
* **Black triangles + full-screen flicker.** 1.0.0 wrote an invalid poly (`-1`) into
  `leftHang_0..3` / `right_1..3`; the retail engine builds a degenerate (NaN) attach matrix from
  that. The fields now point at a **real dummy that sits far away**, so the artefacts are gone.
* `HidePoly` is configurable: point the fields at `382`, `383` or any other dummy id
  (only `-1` restores the old behaviour).

### Added
* `tools\ds3tae.exe`:
  * `parkdir` — append dummies 382/383 at `(0,-1000,0)` to every `chr\*.chrbnd.dcx`, with a
    per-file verification (bone list, materials, meshes and buffer layouts must be unchanged and
    every original dummy entry must stay untouched; otherwise the file is left alone);
  * `stripdir` — remove exactly those dummies again (used to undo the model patch);
  * `scanid`, `flverdiff`, `dummies`, `inspect` — validation and troubleshooting.
* `install.ps1` now performs the character-model patch itself, so `install.cmd` really is
  one click.
* `PairedFields` — choose which models of a paired weapon are hidden (`1` hides only the spare
  blade and keeps the scabbard).
* `Probe` diagnostic mode: writes nothing, logs who reads the attach fields, with call stacks and
  a pointer map.
* Documentation: `docs\MANUAL-INSTALL.txt`, `docs\TECHNICAL-NOTES.md` (mechanism + verified
  evidence + reverse-engineering results), both also available in `docs\zh-CN\`.

### Changed
* Default parking dummy is **382**, appended to **all 165 character models** (player and NPC).
  Because the parameter table is shared, this makes any character resolve a *valid* dummy: NPCs
  no longer produce artefacts, at the cost of also not drawing their sheathed left item.
* Parameter values are re-asserted every second by default; `HidePairedOffhand` defaults to on.

### Documented
* Root cause of the occasional silent failure: the engine **caches** the resolved attach values
  per character and rarely re-reads the shared parameter table, and it keeps several copies of
  that table in memory — so a write can land on a copy the engine is not using.
* Reverse-engineering results, for a future player-only version: the hang-dummy selector
  `exe+0xE31690`, its single call site `exe+0xE35125`, the accessor wrapper `exe+0xE350D0`
  (`rcx` = character-side item-slot object, `r8` = model index, `r9` = side 0/1, `rdx` = output
  pointer) and the field offsets `+0x0A/+0x14/+0x1E/+0x28 = leftHang_0..3`,
  `+0x0C/+0x16/+0x20/+0x2A = rightHang_0..3`.

## 1.0.0

* First release: writes `-1` (an invalid poly) into `WepAbsorpPosParam`'s `leftHang_0..3` /
  `right_1..3`, so the sheathed model of the left-hand item is hidden while the right-hand weapon
  is two-handed; hides the spare model of a one-handed paired weapon.
* Ships the `xinput1_3.dll` loader shell (forwards XInput 1..8) and a hot-reloadable ini.
* Known issue: the invalid poly causes black triangles and full-screen flicker (fixed in 1.0.1).
