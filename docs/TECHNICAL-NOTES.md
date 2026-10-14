# Technical notes — HideSheathedLeft 1.0.1

Everything below was verified on Dark Souls III **1.15.0** (Steam, 64-bit) on
2026-10-14. Addresses are given as `exe+RVA` so they survive ASLR; they are specific to this
game build.

---

## 1. Mechanism

### 1.1 Where the game stores attach ("dummy poly") positions

Weapon models are attached to **dummy polys** of the character model. Which dummy is used for
which stance cluster comes from `WepAbsorpPosParam` (`WEP_ABSORP_POS_PARAM_ST`, 91 rows,
row size `0x60`):

| Field | Offset | Meaning |
|---|---|---|
| `leftHang_0..3` | `0x0A`, `0x14`, `0x1E`, `0x28` | models 0..3 of the left-hand item while it is **sheathed** |
| `rightHang_0..3` | `0x0C`, `0x16`, `0x20`, `0x2A` | models 0..3 of the right-hand item while it is sheathed |
| `right_0..3` | `0x04`, `0x0E`, `0x18`, `0x22` | right-hand item in hand |
| `left_0..3` | `0x06`, `0x10`, `0x1A`, `0x24` | left-hand item in hand |
| `both_0..3` | `0x08`, `0x12`, `0x1C`, `0x26` | right-hand models while two-handed |

The dummy ids refer to the **FLVER dummy table** of the character model (`c0000.flver` for the
player), not to bone indices. Vanilla mapping examples: `right_0/left_0 = 20/21` (hands),
`rightHang_0/leftHang_0 = 30/31` (back), `both_0 = 24`.

### 1.2 Why 1.0.0 produced black triangles

1.0.0 wrote `-1` (an invalid poly) into `leftHang_*` / `right_1..3`. The retail engine does not
treat that as "draw nothing": it builds the attach matrix from uninitialised/NaN data, which
shows up as **black triangles and full-screen flicker**.

**1.0.1 instead parks the model at a real dummy.** Two dummies (`382`, `383`) are appended to every
character model at `(0, -1000, 0)` with parent bone `0` (`Master`), and the parameter fields point
at them. The model is still attached — it is simply 1 km below the character, outside the world.

### 1.3 Why the effect is applied every second

The engine **caches** the resolved attach values inside the character structure and only re-reads
the parameter table when that data is rebuilt (equipment change / character assembly). It also
keeps **several copies** of the table in memory. The mod therefore re-asserts the values once per
second (`IntervalSeconds`) and re-scans for tables if the ones it holds become stale. Two
consequences are documented in the README: an occasional "silent no-op" (the copy the engine reads
was not among the ones found) and a short delay before the effect appears.

---

## 2. Reverse engineering results

The engine's attach resolution was located with a **self-locating probe** (no hardcoded
addresses): the mod puts `PAGE_GUARD` on the pages holding a parameter table's row data, installs a
vectored exception handler that records the faulting address, RIP, registers and stack, and
re-arms the guard with a single-step trap so that *every* access is captured (see
`research/runtime/` for the logging helpers, `tools/maintainer/` for the publishing scripts).

| Item | Address | Notes |
|---|---|---|
| Hang-dummy **selector** | `exe+0xE31690` | reads the 8 `leftHang_*/rightHang_*` values of a row and returns `value[modelIndex * 2 + side]`, where `side` is `0` = left, `1` = right |
| **Only call site** of the selector | `exe+0xE35125` | inside the accessor wrapper below |
| Accessor **wrapper** | `exe+0xE350D0` | `rcx` = character-side item-slot object, `r8` = model index, `r9` = side, `rdx` = output pointer |
| Field offsets | `+0x0A/+0x14/+0x1E/+0x28` = `leftHang_0..3`, `+0x0C/+0x16/+0x20/+0x2A` = `rightHang_0..3` | confirmed by the probe: reading row `0x30` yielded `+0x0A = 48`, `+0x14 = 31`, `+0x16 = 30` |

Because the resolution happens on a generic parameter accessor, **the parameter table cannot carry
two different answers for the player and for NPCs**. A player-only version therefore has to either

* patch the per-character cached attach data (the value the engine actually uses), or
* hook `exe+0xE35125` and substitute the parking dummy only when the caller belongs to the player.

---

## 3. Verification performed

* **Parameter read-back (live process, pid-precise):** rows `48`, `20`, `1029` show
  `leftHang_0..3 = 382` and `right_1..3 = 382`, while `rightHang_0` keeps its vanilla value —
  i.e. only the intended fields are rewritten.
* **Structure diff (SoulsFormats):** the player model has 384 dummies (vanilla: 382); the two
  appended entries are `382`/`383` at `(0,-1000,0)`, and `dummy entries changed: 0` — no vanilla
  entry was touched. Bone list, materials, meshes and buffer layouts are identical.
* **Collision scan:** none of the 165 `chr\*.chrbnd.dcx` files nor the 2 344 `parts\*` files used
  dummy `382`/`383` before patching (highest id anywhere: 940).
* **Character-model patch:** `patched=164 already-had=1 failed=0`, 328 dummies appended, each file
  verified before writing.
* **In game:** with the mod off the shield hangs on the back; with the mod on it is gone, and a
  second independent run reproduces it (screenshots in the release's `evidence\` folder).
* **Revert:** `restore.ps1` plus `tools\ds3tae.exe stripdir` returns the game folder to a state
  where no `chr\*.chrbnd.dcx` contains `382`/`383` (verified by `scanid`).

---

## 4. Tooling

`tools\ds3tae.exe` (source in `validator\Main.cs`, uses SoulsFormats):

| Mode | Purpose |
|---|---|
| `parkdir <root> <out\|INPLACE> <ids> [pos] [parentBone] [filter] [DRYRUN]` | append the parking dummies to every bundle, with per-file verification |
| `stripdir <root> <out\|INPLACE> <ids> [filter] [DRYRUN]` | remove exactly those dummies again |
| `scanid <root> <ids> [filter]` | which files reference these dummy ids |
| `flverdiff <a> <b>` | structural diff (bones / materials / meshes / layouts / dummies) |
| `dummies <file>` | list dummy nodes with bone, position, parent bone scale |
| `inspect <file>` | list sections/entries of a bundle |
| `dumpids <root> <out> [filter]` | dump every dummy id of every file (set analysis) |

`research\` contains the scripts used during development, grouped by purpose:

* `runtime\` — live-process helpers (`ds3mem.py`, `ds3probe.py`, `dumpwep.py`, `wepabsorp.py`,
  `probe_holders.py`, `showrow.py`, `showcopies.py`, …). They need the game running; most of them
  pick the process that owns a window titled `DARK SOULS III`.
* `static\` — offline analysis (`disasm.py` = Capstone disassembly of the game exe by RVA,
  `findcalls.py` = find every `call` to an RVA, `findentry.py`, the TAE tools, blend/behaviour
  dumps).
* `analysis\` — the planning scripts behind the design decisions (`plan_moveonly.py` shows why a
  model-only fix can only cover 33 % of the `leftHang` uses, `plan_common_id*.py` why a "free and
  common" dummy id cannot be found for all models).
* `imaging\` — screenshot comparison helpers.

---

## 5. Open work (player-only version)

The remaining problem is identifying the player at the moment of attach resolution. Options that
were evaluated:

1. **Model-only** (move the vanilla hang dummies inside the player's model): only ~33 % of the
   `leftHang` field uses can be covered, because ids such as `31` (89 of 203 uses) are also used
   for in-hand positions. Rejected.
2. **A free dummy id that every model has** (`220`): exists in 160/165 models and sits inside the
   torso — but real weapons are larger than a torso and were visible poking through. Rejected.
3. **Patch the per-character cached attach values** (recommended next step): identify the cache by
   diffing memory before/after an equipment change, then write the parking dummy only into the
   player's copy. No game code is patched.
4. **Hook `exe+0xE35125`**: substitute the parking dummy only for the player. Requires a reliable
   per-session player pointer; the probe in `Probe=1` mode logs the selector stack and a
   `WorldChrMan` pointer map for exactly that purpose.

`docs\TAE-PLAN.md` documents an alternative route that was evaluated and parked: TAE event 710
(`HideEquippedWeapon`) is per-character by construction (it lives in `c0000.anibnd.dcx`), but its
window semantics mean the event would have to be present in every animation played while the item
is sheathed, including locomotion shared with the one-handed stance.
