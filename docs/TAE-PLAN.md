# TAE route: hiding the sheathed left-hand item the way the game itself does

## The mechanism (confirmed)

Dark Souls III's TAE event **710 `HideEquippedWeapon`** has four boolean parameters:

```xml
<event id="710" name="HideEquippedWeapon">
  <b name="LeftHand"/>
  <b name="RightHand"/>
  <b name="LeftHand_WithScabbard"/>
  <b name="RightHand_WithScabbard"/>
</event>
```

It hides the *model* of an equipped weapon while the item stays equipped -- i.e. it is
exactly the "hide, do not unequip" behaviour we want, and it is entirely handled by
the engine (no memory writes, no hooks, no out-of-range dummy polys, so no black
triangles).

Event parameters were read from DSAnimStudio's `TAE.Template.DS3.xml`
(`event id="710" name="HideEquippedWeapon"`).

## Why it is not a one-shot flag

Scanning the player's 251 TAE files in `chr/c0000.anibnd.dcx`:

```
event 710 HideEquippedWeapon : 1895 occurrences in 110 of 251 TAE files
event 711 HideModelMask      :  567 occurrences in  30 of 251 TAE files
```

The event is fired *per animation*, so the hide state has to be set in every animation
that should hide the weapon.  Consequence: hiding the left hand while two-handing
means adding event 710 with `LeftHand = 1` to the *two-hand* animations.

## Which animations (the work list)

Two name tables ship with the game and map animation ids to names:

* `action/eventnameid.txt`  -- 134 entries contain `Both`/`HandChang`
* `action/statenameid.txt`  -- 119 entries contain `Both`/`HandChang`

They are saved next to this file as:

* `TAE-animations-eventnameid.txt`
* `TAE-animations-statenameid.txt`

The core entries to edit first (smallest test case):

| id   | name |
|------|------|
| 1445 | `W_IdleBothHand`        | two-hand idle |
| 1725 | `W_ToBothHand`          | entering two-hand |
| 1726 | `W_ToBothHandStart`     | ... |
| 1429 | `W_HandChange`          | stance change |
| 1434 | `W_HandChangeStart`     | ... |
| 1435 | `W_HandChangeUpper`     | ... |
| 478  | `HandChange`            | ... |
| 869  | `ToBothHandEnd`         | leaving two-hand |

then all `W_AttackBoth*` / `AttackBoth*` entries (about 40 of them).

## Container format (already reverse engineered)

`chr/c0000.anibnd.dcx` is a **DCX-compressed BND4**:

* DCX: zlib stream starts right after the 0x24-byte DCX header (magic `78 DA`/`78 9C`).
* BND4 header at 0x00; file count at 0x0C; record size at 0x20 (= 0x24).
* Each record (stride 0x24) - the record that owns a given name offset begins at
  `nameOffsetField - 0x20`:

```
rec+0x00  u32  flags
rec+0x04  i32  id
rec+0x08  u64  size          (also uncompressed size -> entries are stored raw)
rec+0x10  u64  size (dup)
rec+0x18  u32  dataOffset     <- file data starts here
rec+0x1C  u32  file id
rec+0x20  u32  nameOffset     -> UTF-16 name, e.g. N:\FDP\...\chr\c0000\tae\a00.tae
```

* Embedded TAE files start with the 4-byte magic `TAE ` (with a space); 251 of them.
* TAE header so far (a00.tae at data offset 0xC5F0):

```
+0x00  "TAE "
+0x04  u32   version/magic
+0x08  u32   0x0001000C
+0x0C  u32   file size
+0x20  u64   0x50   event bank offset (relative)
+0x28  u64   0x80   animation table offset (relative)
+0x30  u64   0x15   event type count (21)
+0x40  u8[]  event types
+0x80  animation records: {u32 id, u32 ?, u64 eventOffset, u32 duration, u32 ?, u32 eventCount}
```

Animation id 1 in a00.tae is `_Chang_Pose_L_leg`, matching `eventnameid.txt`.

## Two ways to actually make the edit

1. **DSAnimStudio** (TAE editor, understands `.anibnd.dcx`): open
   `chr/c0000.anibnd.dcx`, select the animations from the list, add
   `HideEquippedWeapon` with `LeftHand` checked, save.  Note: the repository
   (`sovietspaceship/DSAnimStudio`) publishes no ready-made release, so a build of it
   (or a third-party prebuilt) is required.
2. **Scripted edit**: parse the BND4 (layout above), parse the TAE animation records and
   their event lists, insert one event per animation, repack and recompress the DCX.
   Everything is a plain little-endian format, so this is doable in Python; the risk is
   a malformed bundle, so keep a backup of `chr/c0000.anibnd.dcx`.

## If the TAE route is not finished

Ship the mod with `HideLeftHang=0` by default (the dummy-poly trick is the only thing
that produces black triangles) and keep this document as the reference for the correct
implementation.
---

## VERIFIED PROGRESS (tooling is done)

### Working tools (in `tools/`, standard-library Python only)

| tool | what it does |
|---|---|
| `ds3bnd.py <bundle> list` | DCX-decompress + list every inner file with its true offset/size |
| `ds3bnd.py <bundle> find <name> <u32>` | locate a u32 (e.g. event 710) inside one inner file + dump around the first hit |
| `ds3bnd.py <bundle> dump <name> <relOff> <len>` | hex dump of an inner file |
| `ds3bnd.py <bundle> extract <name> <out>` | write an inner file out |
| `taescan.py <bundle>` | per-entry event-id census |
| `bndfind.py` | name -> record correlation (layout discovery) |

`chr/c0000.anibnd.dcx` parses cleanly: 272 entries, first entries
`Skeleton.HKX @0x9B90`, `a00.tae @0xC5F0 (4,320,224 bytes)`, `a02.tae`, ... `a15.tae @0x52D170 (185,568 bytes)`.

### BND4 record layout (verified against real names)

```
record i at 0x40 + i*recordSize          recordSize at header+0x20 (= 0x24)
  rec+0x00 u32 flags        (0x40 = uncompressed)
  rec+0x04 i32 id           (-1)
  rec+0x08 u64 size
  rec+0x10 u64 size (dup)
  rec+0x18 u32 dataOffset   (absolute, inside the decompressed BND4)
  rec+0x1C u32 fileId
  rec+0x20 u32 nameOffset   -> UTF-16 path, N:\FDP\...\chr\c0000\tae\aNN.tae
```

### TAE event census (player bundle)

```
event 710 HideEquippedWeapon : 1895 occurrences in 110 of 251 TAE files
event 711 HideModelMask      :  567 occurrences in  30 of 251 TAE files
```

### Event records (still being finalised)

`ds3bnd.py ... find a15.tae 710` finds 12 occurrences, e.g. at `+0x1E09` and then a run at
`+0x2C391, +0x2C3A9, +0x2C3C1, +0x2C3D9, +0x2C3F1` -- **stride 0x18 (24 bytes)**, i.e. one
24-byte record per event, and the engine fires the event repeatedly inside one animation.

Every value is little-endian and the surrounding fields are zero-extended, e.g.

```
+02C391  c6 02 00 00 00 00 00 e4 c1 02 00 00 00 00 00 ec
```

**Next step for whoever continues this:** dump two adjacent records whose *parameters are
known to differ* (an event with `LeftHand=1` and one with all flags 0) and diff them; the
only differing bytes are the parameter block.  After that: insert a 24-byte record into the
`LeftHand = 1` group of each animation from `TAE-animations-*.txt`, rebuild the BND4
(offsets/sizes + the u32 at TAE+0x0C = file size), recompress the DCX, replace
`chr/c0000.anibnd.dcx` (keep a backup), and test.
---

## ROUND 2 - authoritative format (SoulsFormats TAE3), parser 95% working

Reference sources saved under `ref/`:
`BND4.cs`, `TAE3.cs`, `TAE3.Event.cs` (from JKAnderson/SoulsFormats).  DS3 uses **TAE3**.

### TAE3 container (confirmed against the game's own files)

```
+0x00 "TAE "                     +0x04 00 00 00 FF
+0x08 int32 version (0x1000C)    +0x0C int32 fileSize      <- must be fixed on edit
+0x10 int64 0x40                 +0x18 int64 1
+0x20 int64 eventBankOffset (=0x50)
+0x28 int64 animsOffset   (=0x80)
+0x30 int64 eventTypeCount       +0x38 int64 0
+0x40 byte[8] Flags
event bank @+0x50: { int32 bankId, int32 animCount, int64 animsOffset, int64 animGroupsOffset, ... }
animation table @ animsOffset: animCount * { int64 animId, int64 animHeaderOffset }
animation header @ animHeaderOffset:
    int64 eventHeadersOffset
    int64 eventGroupsOffset
    int64 timesOffset
    int64 animFileOffset
    int32 eventCount
    int32 eventGroupCount
    int32 timesCount
    int32 0
event header (24 bytes each): { int64 startTimeOffset, int64 endTimeOffset, int64 eventDataOffset }
event data block:             { uint64 type, int64 selfPtr(=pos+8), params..., pad to 0x10 }
HideWeapon (710) params:      { byte Unk00, byte Unk01, byte Unk02, byte Unk03,
                                int32 0, int32 0, int32 0 }        <- 4 bytes + 12 zero bytes
```

The four bytes map to the DSAnimStudio template parameters
`LeftHand / RightHand / LeftHand_WithScabbard / RightHand_WithScabbard`,
so **hiding the sheathed left-hand item = setting that event's first parameter byte to 1**.

### Tooling state

* `tools/ds3bnd.py` - DCX + BND4: `list`, `find`, `dump`, `extract` - **verified working**.
* `tools/tae3.py` - TAE3 parser: prints each animation's events with type, times and params.
  Header/animation/event-header parsing is **verified** (times come out sane, e.g.
  `anim 4200 type=300 params=0b 00 01 00 (0.267..0.367)`), but the event **type** field is read
  from the wrong byte inside the data block (prints 0/300/128 where 100/212/710 are expected).
  Fix by dumping the raw bytes around one event data block and locating the `c6 02 00 00`
  (=710) sequence: the type is 8 bytes earlier or later than currently assumed.

### Once the type offset is fixed

1. list every animation whose events include type 710 and show its 4 parameter bytes;
2. for the two-hand animations (`W_IdleBothHand` = 1445, `W_ToBothHand` = 1725, `W_HandChange*`,
   all `W_AttackBoth*` - full lists in `TAE-animations-*.txt`), set the first parameter byte to 1,
   or insert a new 710 event if the animation has none;
3. rebuild: fix TAE+0x0C, the BND4 record size, the BND4 header offsets, recompress the DCX;
4. replace `chr/c0000.anibnd.dcx` (back it up first) and test in game.
---

## ROUND 3 - the mechanism is CONFIRMED in the game's own bytes

Parsing every TAE of `chr/c0000.anibnd.dcx` and printing the HideWeapon (710) events
with their 4 parameter bytes gives the mapping directly:

```
a00.tae anim 20     _R_arm_00      params = 00 01 00 00    RightHand = 1
a00.tae anim 200                   params = 00 01 00 00    RightHand = 1
a00.tae anim 4500                  params = 01 01 00 00    LeftHand = 1 + RightHand = 1
a00.tae anim 28000 .. 28212        params = 01 01 00 00    LeftHand = 1 + RightHand = 1
```

So the four bytes are `LeftHand / RightHand / LeftHand_WithScabbard / RightHand_WithScabbard`
(confirmed against DSAnimStudio's `TAE.Template.DS3.xml`), and **the game itself already
fires the "hide both hands" version in several animations** -- an existing event with
`01 01 00 00` is a ready-made template to copy.

### Parser status: working

`tools/tae3.py` and `tools/taefind.py` parse the animation table, the 24-byte event headers
and the event data blocks correctly.  Key detail that cost time: the event data block is
**not** at `dataOffset` as a TAE-relative offset in the way first assumed -- for
`a00.tae` the block containing the type u64 was found at exactly `dataOffset` for
animations 20 (0x1EA30) and 200 (0x20980), so `dd = taeBase + dataOffset` is correct and
the earlier "self-pointer signature" filter was a false lead (it has been removed).

### Important: two different id spaces

* `action/*nameid.txt` ids (1..4267) are **script/state** ids, NOT animation ids.
* TAE animation ids are a different numbering (seen: 0, 20, 200, 4500, 28000..28212, ...).
  To name an animation id, look up the `aXXX_XXXXXX.hkx` file names inside the
  `chr/c0000_aXX.anibnd.dcx` bundles (the number in the file name is the animation id).

### Next concrete step

1. list the `hkx` names in `chr/c0000_a*.anibnd.dcx` and map them to animation ids;
2. pick the two-hand idle/movement/attack animations (the ones whose hkx names match the
   `W_*Both*` / `HandChange*` names from the name tables);
3. for each, append one 24-byte event header pointing at a copy of an existing
   `01 01 00 00` HideWeapon data block (or `01 00 00 00` for left-hand-only), fix the
   counts/offsets, rebuild the BND4 + DCX, back up and test.
---

## ROUND 4 - animation id <-> name mapping FOUND (inside the behaviour bundle)

`chr/c0000.behbnd.dcx` (7,042,896 bytes, 6 entries: 3 x `c0000.hkt`, 3 x `c0000.hkx`)
contains a Havok string pool in which **each animation's state names are grouped and
terminated by an `hkx` file name marker**:

```
[group] W_AttackRightLight1 W_AttackRightHeavy1 W_AttackRightLight2 W_AttackRightLight3
        W_AttackRightHeavy1Sub W_AttackRightHeavy2 W_AttackRightLightKick ...
ID ->   $a000_000031.hkx_WC          <- so id 31 = the one-hand right attack set
[group] W_AttackBothLight1 W_AttackBothLight2 W_AttackBothLight3 W_AttackBothDash
        W_AttackBothLightStep W_AttackBothLightKick
ID ->   *W_AttackBothHeavyKick$a000_000032.hkx_WC     <- id 32 = the TWO-HAND attack set
[group] W_ItemWeaponEnchant W_ItemDrinkNothing ...
ID ->   $a000_000010.hkx_WC          <- id 10 = the item-use set
```

Other examples recovered the same way:

| marker | names in the group before it |
|--------|------------------------------|
| `a000_000060.hkx` | `W_GuardOn_Upper`, `State00_WC`, `State01_WC` |
| `a000_000061.hkx` | `W_FallLoop`, `W_FallJumpStart`, `W_LandDefault`, `W_FallAttack*` |
| `a000_000006.hkx` | `W_DamageExLarge`, `W_DamageWeak`, ... `W_GuardBreakWall` |
| `a000_000011.hkx` | `W_DeathCommon`, `W_DeathSmallBlast`, ... |
| `a000_000007.hkx` | `W_AttackArrowRightFire`, `W_AttackRightWhileGuard`, ... |
| `a000_000004.hkx` | `W_WeaponChangeStart_Upper` |

### Two-level id scheme

The `a000_*` markers are the **common/unarmed** animation set.  Weapon-specific sets use
`aXXX_0IIIII.hkx` names stored in the split bundles `chr/c0000_aXX.anibnd.dcx`
(`a0x` holds categories 00-0F, `a1x` holds 10-1F, ... `a9x` holds 90-9F), and the TAE
animation id is `category * 1000 + index` (observed: 28000 = category 28, 30410/30420,
60000-60430, 60750, 65020-65060).

### Consequence - this is now an arithmetic problem

For a weapon whose motion category is `C`, the two-hand attack animations sit at
`C * 1000 + 31/32/...` exactly like the common set (31 = one-hand right attacks,
32 = two-hand attacks).  So:

1. look up the weapon's motion category (from the weapon param, `EQUIP_PARAM_WEAPON_ST`);
2. compute the candidate two-hand animation ids;
3. verify each candidate in the TAE (its event list, and the hkx marker in the behbnd);
4. insert the HideWeapon (`01 01 00 00`, or left-only `01 00 00 00`) event.

Note: the `01 00 00 00` (left-hand-only) form already exists in 23 animations
(ids 30410 30420 42047 42347 50060 60000-60003 60430 60750 65020 65050 65060), and
`01 01 00 00` in 254 animations (4500 4510 28000-28212), i.e. both templates are on hand.
---

## ROUND 5 - the complete id map is extractable (no param lookup needed)

`chr/c0000.behbnd.dcx` contains **13,113 `hkx` markers**, each preceded by the group of
state names that reference that animation.  Extracting them gives a full
**animation id -> state names** map:

```
id 32     W_AttackBothLight1 W_AttackBothLight2 W_AttackBothLight3 W_AttackBothDash
          W_AttackBothLightStep W_AttackBothLightKick
id 31     W_AttackRightLight1 W_AttackRightHeavy1 W_AttackRightLight2 ...
id 60     W_GuardOn_Upper W_GuardStart_Upper W_GuardEnd_Upper State00_WC State01_WC
id 27133  Rolling RollingOverweightFront/Back/Left/Right RollingHeavy* (with _CMSG names)
id 99050  a316_099050.hkx  <- animation set a316, animation 99050
```

**Final naming rule:** the `hkx` name is `aXXX_IIIIII.hkx` where `IIIIII` **is** the
animation id used by the TAE (verified: 32, 31, 60, 27133, 99050).  `aXXX` is the
animation-set group (bundles `chr/c0000_aXX.anibnd.dcx`: `a0x` = sets 000-0FF,
`a3x` = sets 300-3FF, ...).  Behaviour state-machine names carry a `_CMSG` suffix.

### Therefore the remaining work is fully mechanical

1. extract the 13,113 (id, name-group) pairs from `chr/c0000.behbnd.dcx`
   (regex on printable runs + `a(\d{3})_(\d{6})\.hkx`);
2. select the animations whose name group matches the two-hand stance:
   `W_AttackBoth*` (attacks), `HandChange*` (stance switch) and the corresponding
   two-hand idle/move entries in each `aXXX` set;
3. for each selected id, append a 24-byte event header to that animation's event list in
   `chr/c0000.anibnd.dcx`, pointing at a copy of an existing
   `HideWeapon` data block with parameters `01 01 00 00` (both hands) or `01 00 00 00`
   (left hand only).  Ready-made source blocks exist at the animations listed in ROUND 3;
4. fix the event count / offsets / `TAE+0x0C` file size, rebuild the BND4
   (record size + data offsets + header offsets), recompress the DCX, back up the
   original `chr/c0000.anibnd.dcx`, install and test.

Nothing about the mechanism is unknown any more; only the byte-level splice and the
in-game test remain.
---

## ROUND 6 - targets verified, final design fixed

Cross-checking the selected ids against the TAE event lists:

```
anim 29013  HandChangeBothRightToShoulder   7 events   710 = NONE   <- two-hand stance switch, no hide event
anim 33000  AttackBothLeft1                36 events   710 = NONE   <- two-hand attack, no hide event
anim 33020  AttackBothLeftDash             36 events   710 = NONE
anim  4500                                13 events   710 = 01 01 00 00
anim 28000                                16 events   710 = 01 01 00 00
```

This matches the reported symptom exactly: the two-hand animations carry no hide event,
so the sheathed left-hand item keeps being rendered.

**Final design**

* Event: **710 `HideWeapon`**, parameter bytes **`01 00 00 00`** - left hand only.
  `01 01 00 00` must **not** be used: it also hides the right hand, i.e. the weapon the
  player is actually holding would vanish.
* A ready-made `01 00 00 00` data block exists (23 animations use it:
  30410 30420 42047 42347 50060 60000-60003 60430 60750 65020 65050 65060).
* Targets: the two-hand animations.  69 candidates were extracted from
  `chr/c0000.behbnd.dcx` into `docs/TAE-twohand-ids.txt` (`id <TAB> set <TAB> state names`),
  keyed on the state names `AttackBoth*` / `HandChangeBoth*` / `HandChange*`.
  `tools/behmap.py` regenerates that list at any time.
* Note: a few behaviour-marker ids (`a000_000031`, `a000_000032`) are not present as TAE
  animation ids, but the ids that matter (29013, 33000, 33020, ...) are, and each candidate
  can be verified against the TAE before editing.

**Remaining (purely mechanical, no unknowns):** splice one 24-byte event header per target
animation pointing at a copied `01 00 00 00` data block, fix the animation's event count and
offsets plus `TAE+0x0C`, rebuild the BND4 record sizes/offsets and header offsets, recompress
the DCX, back up `chr/c0000.anibnd.dcx`, install and test in game.