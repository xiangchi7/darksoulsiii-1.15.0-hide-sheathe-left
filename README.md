# HideSheathedLeft — Dark Souls III 1.15.0

While you two-hand the right-hand weapon, the **left-hand item's sheathed model is no longer
drawn on your back**. Works for anything hand-equippable: weapons, shields, catalysts, bows,
staves.

> Dark Souls III **1.15.0** (Steam, 64-bit). Local memory + model changes only. Online play has
> a server-side save sanity check — use it offline.

---

## What it does

| Situation | Vanilla | With this mod |
|---|---|---|
| Right-hand weapon **two-handed**, left hand occupied | left item hangs on your back | left item is **not drawn** |
| Left item **in use** (blocking / swinging) | drawn normally | **drawn normally** (unaffected) |
| **Paired weapon** in the right hand, one-handed | spare model sits on the body | spare model **not drawn** (`PairedFields` can hide only the blade and keep the scabbard) |

**How (1.0.2):** the `leftHang_0..3` and `right_1..3` fields of `WepAbsorpPosParam` are pointed at
a **parking dummy** (id `382`, with `383` as a spare) that sits **1000 m below the character**.
The model is still attached, just far outside the world — so nothing is drawn, and because the
dummy is a *real* dummy (not an invalid poly like `-1` in 1.0.0) the engine builds a valid matrix,
which removes the 1.0.0 **black triangles / full-screen flicker**.

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

Double-click **`restore.cmd`** (or `restore.ps1`) to put the backed-up originals back.
To also undo the model patch:

```powershell
tools\ds3tae.exe stripdir "<game>\chr" INPLACE "382,383" "chrbnd"
```

---

## Configuration

`HideSheathedLeft.ini` (saved changes apply within a second, no restart needed):

| Key | Default | Meaning |
|---|---|---|
| `HideLeftHang` | `1` | the core effect: hide the sheathed left-hand item |
| `HidePairedOffhand` | `1` | hide the spare model of a one-handed paired weapon |
| `PairedFields` | `1,2,3` | which right-hand models to hide: `1` = blade only (keeps the scabbard), `none` = leave the right hand alone |
| `HidePoly` | `382` | parking dummy id (`383` spare, `-1` reproduces the 1.0.0 artefacts) |
| `IntervalSeconds` | `1` | how often the parameter values are re-asserted |
| `Probe` | `0` | `1` = observation only (writes nothing, logs to `HideSheathedLeft.log`) |
| `ExtraMods` | *(empty)* | must stay empty — loading additional DLLs on 1.15.0 crashes the game |

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
| `v1.0.2` | current: identical behaviour, but the table search is resident-only, so the game's memory footprint is indistinguishable from vanilla (peak working set 1624 MB vs vanilla 1634 MB; 1.0.1 was 6007 MB). |

## Notes

* This repository ships **no game assets**: `tools\ds3tae.exe` only appends two dummies to
  **your own** `chr\*.chrbnd.dcx` files (and verifies that everything else stays byte-identical).
* `install.ps1` backs up every file it overwrites as `*.vanilla-backup`, so `restore.ps1` can
  always undo it.
* Memory: the table scan only reads pages the OS currently holds resident, so it cannot pull the
  game's paged-out resource pools back into RAM. `HideSheathedLeft.log` prints what each scan cost
  — see `docs\MEMORY-FIX-1.0.2.md`.
* Only one `xinput1_3.dll` can live in the game folder: if another mod (e.g. a key-prompt mod)
  already owns that slot, the installer renames it to `xinput1_3.dll.dkp-off` and keeps it.
  The two mods cannot be active at the same time.

## License

MIT — see [`LICENSE`](LICENSE). Not affiliated with FromSoftware or Bandai Namco; single-player,
offline use only.
