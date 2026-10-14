# Changelog

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
