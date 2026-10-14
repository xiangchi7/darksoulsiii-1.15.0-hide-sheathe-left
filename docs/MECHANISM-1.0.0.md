# Mechanism — how "sheathed left-hand item" hiding was found and proven

This document records what the mod actually rewrites, why those fields are the
right ones, which plausible-looking alternatives do nothing, and how each claim
was verified. It exists so that the mod is not a magic set of hex offsets.

Everything below was verified on **Dark Souls III 1.15.0** (Steam, 64-bit,
`DarkSoulsIII.exe` file version 1.15.0.0) — by editing the live parameter table
while the game was running and observing the character on screen.

---

## 1. The parameter

```
WepAbsorpPosParam            (paramdef name WEP_ABSORP_POS_PARAM_ST, 91 rows)
row size 0x60
```

Per weapon and per **model index 0..3** it stores the *absorption dummy poly* —
the attach point on the character skeleton — for each stance:

| row offset | field | meaning |
|---|---|---|
| `0x00` | `hangPosType` | sheathe location type (enum `HANG_POS_TYPE`: Back/LeftHip/RightHip/LeftShoulder) |
| `0x01` | `isSkeletonBind` | unused by the DS3 code path (used by Elden Ring only) |
| `0x04`,`0x06`,`0x08` | `right_0`, `left_0`, `both_0` | model 0 attach poly, one-handed right / one-handed left / two-handed right |
| **`0x0A`,`0x14`,`0x1E`,`0x28`** | **`leftHang_0..3`** | model 0..3 attach poly **while the left-hand item is sheathed** |
| `0x0C`,`0x16`,`0x20`,`0x2A` | `rightHang_0..3` | model 0..3 attach poly while the right-hand item is sheathed |
| `0x0E`,`0x18`,`0x22` | `right_1..3` | model 1..3 attach poly, one-handed right |
| `0x2C..0x2F` | `wepInvisibleType_0..3` | filter tag for TAE event 712 (see §4) |
| `0x30..0x36` | `leftBoth_0..3` | model 0..3 attach poly, two-handed left |
| `0x38..0x4F` | `dispPosType_*` | display-position tag (see §4) |
| `0x50..0x5F` | `reserve[16]` | padding |

A value of `-1` is explicitly legal (`Minimum = -1`, `Maximum = 31999`).

## 2. The cluster is chosen by weapon style alone

DSAnimStudio's reimplementation of the engine's character assembler picks the
cluster purely from `WeaponStyle`:

```csharp
if (style == WeaponStyleType.OneHand) {
    left  slot => NewAbsorpPos[Left];      right slot => NewAbsorpPos[Right];
} else if (style == WeaponStyleType.LeftBoth) {
    left  slot => NewAbsorpPos[LeftBoth];  right slot => NewAbsorpPos[RightHang];
} else if (style == WeaponStyleType.RightBoth) {
    left  slot => NewAbsorpPos[LeftHang];  right slot => NewAbsorpPos[RightBoth];
}
```

So **two-handing the right weapon makes the left slot use `leftHang_*`** — the
exact state the mod targets.

## 3. An invalid dummy poly means "do not render"

From the same project's assembler:

```csharp
var dummyPolyID = wpnSlot.GetFinalAbsorpModelDmyPoly(modelIdx);
if (dummyPolyID >= 0 && dummyPolyMan.NewCheckDummyPolyExists(dummyPolyID)) {
    absoluteWeaponTransform = ...dummyPolyMatrix...;
} else {
    absoluteWeaponTransform = Matrix.CreateScale(0);
    hiddenByAbsorpPos = true;          // -> wpnMdl.IsHiddenByAbsorpPos = true
}
...
bool renderWpn = !wpnMdl.IsHiddenByAbsorpPos;
if (renderWpn) wpnMdl?.Draw(...);
```

Writing `-1` (or any id the character skeleton does not have) therefore makes
the model scale to zero and disappear, with **no TAE event and no code patch
involved**.

**Verified in the retail game**: with `leftHang_0..3 = -1` written into the live
table and the stance re-evaluated (toggle two-handing off and on so the
assembler rebuilds), the shield that normally hangs on the back is gone, while
the right-hand weapon and the one-handed left-hand pose are unaffected.
Restoring the original values brings it straight back.
See `docs/evidence-sheathed-left-hidden.png`.

## 4. Fields that look like the answer but do nothing

Measured histograms over all 91 rows of the live table, then edited one field at
a time and re-observed:

| field | observed values | result when changed |
|---|---|---|
| `dispPosType_*` | `0`, `1`, `3` (enum: `RightHand=0, LeftHand=1, Other=3`) | **no visible effect.** DSAnimStudio reads these into its struct but never consumes them, and nothing else in the engine has been shown to either. Values were also set to `0`, `1`, `3` and `-1` with no change. |
| `hangPosType` | `0..3` (enum: `Back=0, LeftHip=1, RightHip=2, LeftShoulder=3`) | **no visible effect** — read but not consumed in the paths inspected. |
| `wepInvisibleType_*` | model 0: `0` in every row; models 1–3: `0`,`1`,`2` (enum `None=0, Sheath=1, DualSwordLeftHand=2`) | setting it to `1` changed nothing. It is a **filter tag**: TAE event 712 carries per-model `WepInvisibleTypeFilter` values and compares them against the param row; a match overrides that model's absorption position. Without such an event firing, the field is inert. |
| `isSkeletonBind` | `0` in every row | only consumed for Elden Ring. |

For comparison, the enum names come from DSAnimStudio's own definitions:

```csharp
public enum HangPosTypes { Back = 0, LeftHip = 1, RightHip = 2, LeftShoulder = 3, RightShoulder = 4 }
public enum DispPosTypes : byte { RightHand = 0, LeftHand = 1, Other = 3 }
public enum WepInvisibleTypes : sbyte { Undefined = -1, None = 0, Sheath = 1, DualSwordLeftHand = 2 }
public enum DS3MemeAbsorpTaeType : sbyte { None = -1, Left = 0, Right = 1, AnyBoth = 2, AnyHang = 3,
                                           MaintainPreviousValue = 4, PositionForFriedeScythe = 5, Unknown6 = 6 }
```

The two TAE events involved in the retail game are **710 `HideEquippedWeapon`**
(four booleans: left/right hand, left/right hand "with model 1") and
**712 `OverrideWeaponModelLocations`** (the `wepInvisibleType` filter described
above).

## 5. Locating the table at runtime (no version-specific offsets)

The mod never uses hardcoded addresses. It walks the process address space and
looks for the ASCII string `WEP_ABSORP_POS_PARAM_ST`, then reconstructs the
`ParamTable` from it:

```
ParamTable
  +0x0A  u16  row count
  +0x10  u64  offset of the snake-case name, relative to the table itself
  +0x40  ParamRowInfo[]  { u64 row_id; u64 offset; u64 unused }        (0x18 each)
  data  = table + row_info[i].offset                    (row size 0x60 here)
  name  = table + name_offset
```

The self-referential `name_offset` (`u64 at table+0x10 == distance from the
table to the name`) is what pins the table start exactly, so a hit on the name
string is enough. On 1.15.0 this finds **four byte-identical copies** of the
table; all four are written.

The layout comes from
[fromsoftware-rs](https://github.com/vswarte/fromsoftware-rs)
(`crates/darksouls3/src/sprj/regulation_manager.rs`). Note that its published
RVA table targets 1.15.2 and does **not** match this build — every global read
from it returned nonsense here, which is why the name scan is used instead.

## 6. Measurements and method

* **State changes matter.** Changing a parameter value alone does not always
  rebuild the character assembler; the value was applied and then two-handing
  was toggled off and on (`5` on the keyboard) to force a rebuild before
  observing. This is also how the retail game's behaviour was compared against
  the DSAnimStudio rule.
* **Screenshot diffing** was used for the objective call: capture the character
  region before and after, and compare changed-pixel counts, mean difference and
  the bounding box of the change (`tools/pngdiff.py`, `tools/pngsbs.py`). A
  back-to-back noise floor was measured first (~7% of pixels in the character
  region, from idle animation and dynamic lighting), so a change was only
  accepted when it was large and localised.
* **Live editing** of the table was done through a small memory toolkit
  (`tools/ds3mem.py`, `tools/wepabsorp.py`) driven by a privileged helper
  process (`tools/ds3agent.py`).

## 7. Is there a separate PC and NPC copy of the table?

Question: since the parameter table is shared, would NPCs be affected too — and
could a hypothetical PC/NPC split of the table be exploited to make the mod
strictly player-only?

DS3's parameter repository (`SoloParamRepository`) stores parameters in
`SoloParamCell`s that can hold several `ParamResCap` pointers, and a few
parameters genuinely exist twice (for example `ATK_PARAM_ST` for NPCs at index
*N* and for PCs at *N+1*). That would have been the clean answer.

A probe (`tools/probe_holders.py`) walked
`table → FD4ParamResCap → ParamResCap → SoloParamCell` in the live process and
found:

* four `WEP_ABSORP_POS_PARAM_ST` tables, all byte-identical (91 rows each);
* no pointer anywhere in committed memory pointing at three of them, and only
  two coincidental, structurally invalid candidates for the fourth.

Conclusion: **there is no reachable PC/NPC split for this parameter** — it is
one logical table loaded in several places. Scoping the effect per character
therefore cannot be done by editing data alone.

## 8. Making it strictly player-only

Two viable routes, both larger than the current change:

1. **Hook the attach decision.** The function that resolves a weapon slot's
   final absorption dummy poly could be made to return "invalid" only when the
   slot belongs to the player's assembled character. The function has no
   published address in any source that was reachable, but it can be located
   from inside the process without a debugger: put a `PAGE_GUARD` on the page
   holding a live `leftHang` field, install a vectored exception handler, and
   record the `RIP` of whatever reads it; then hook that site and inspect its
   arguments. Hardware breakpoints would also work but are a classic
   anti-debug tripwire, so a page guard is the safer probe.
2. **Use the player-only animation set.** The player character uses `c0000`;
   NPCs use other character IDs and do not share its animation files. Adding TAE
   event 710 (`HideEquippedWeapon`, `leftHand = true`) to the player's
   two-hand idle animation is player-only by construction, and event 712 could
   be used the same way with the `wepInvisibleType` filter. This requires
   BND/DCX/TAE read–write tooling.

Until one of those is implemented, the parameter patch stays global; see the
limitations section of the README.

## 9. References

* DSAnimStudio — <https://github.com/sovietspaceship/DSAnimStudio>
  (`DSAnimStudioNETCore/NewChrAsm.cs`, `NewEquipSlot_Weapon.cs`,
  `TaeEditor/TaeActionSimulationEnvironment.cs`,
  `ParamData/ParamData.WepAbsorpPosParam.cs`)
* fromsoftware-rs — <https://github.com/vswarte/fromsoftware-rs>
  (`crates/darksouls3/src/sprj/regulation_manager.rs`,
  `tools/param-generator/params/darksouls3/*.xml`)
* Souls Modding wiki, "How To Create a Trick Weapon in DS3" —
  <https://soulsmodding.wikidot.com/tutorial:how-to-create-a-trick-weapon>
  (community technique: point an absorption dummy poly somewhere harmless so the
  model disappears)
* The Grand Archives DS3 cheat table —
  <https://github.com/The-Grand-Archives/Dark-Souls-III-CT-TGA>
