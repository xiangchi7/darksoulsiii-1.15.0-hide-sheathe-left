# Changelog

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
