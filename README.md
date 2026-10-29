# HideSheathedLeft — Dark Souls III 1.15.0

**[中文](#中文) · [English](#english)**

## 中文

当你双手持其中一只手的武器时，**另一只手上收鞘的武器模型不再显示在背上**。行为是对称的：双手持右手武器时左手武器消失，双手持左手武器时右手武器消失。任何能装备到手上的东西都适用：武器、盾牌、触媒、弓、法杖。

> Dark Souls III **1.15.0**（Steam，64 位）。只改内存和模型，不动存档。线上游戏有服务端存档校验——请离线使用。

### 它做了什么

| 情形 | 原版 | 装了本 mod 后 |
|---|---|---|
| 右手武器**双手持**，左手有东西 | 左手武器挂在背上 | 左手武器**不显示** |
| **左手**武器双手持，右手有东西 | 右手武器挂在背上 | 右手武器**不显示** |
| 收鞘的武器**正在使用**（格挡 / 挥砍） | 正常显示 | **正常显示**（不受影响） |
| **成对武器**单手持（任意一只手） | 备用模型贴在身上 | 备用模型**不显示**（`PairedFields` 只能隐藏刀刃、保留刀鞘） |

**原理**：把 `WepAbsorpPosParam` 里的 `leftHang_0..3` / `rightHang_0..3` 和 `right_1..3` / `left_1..3` 字段指向一个**停放假体**（id `382`，备用 `383`），它位于**角色下方 1000 米**。模型仍被挂载，只是远在世界之外——所以什么都画不出来；又因为假体是*真*假体（不是 1.0.0 里 `-1` 那种非法多边形），引擎能建出合法矩阵，从而消除了 1.0.0 的**黑三角 / 全屏闪烁**。

停放假体会被追加到**每一个角色模型**（`chr\*.chrbnd.dcx`），所以任何角色——玩家还是 NPC——都不会解析到缺失的假体。

### 需求

* Dark Souls III 1.15.0（Steam）。
* **松散文件环境**（存在 `Game\chr\*.chrbnd.dcx`——用 UXM 解包后的正常状态，模型类 mod 都要求这个）。随包的补丁工具会就地修改这些文件。
* Windows PowerShell（系统自带）。只有重新编译工具时才需要 .NET 8/10 运行时。

### 安装

1. 关闭游戏。
2. 双击 **`install.cmd`**（或运行 `powershell -ExecutionPolicy Bypass -File install.ps1`）。

它把 payload 复制进游戏目录，然后给每个 `chr\*.chrbnd.dcx` 追加假体 382/383（每个文件写前都会校验；已经带假体的文件会跳过）。逐步手动安装见 [`docs/MANUAL-INSTALL.txt`](docs/MANUAL-INSTALL.txt)。

随时查看状态：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Status
```

#### 卸载

双击 **`restore.cmd`**（或 `restore.ps1`）。它会重放 `install.ps1` 写的 `<game>\.hsleft-manifest.json`：

* 安装器覆盖过的每个文件，都会从 `<game>\.hsleft-backup\<相同的相对路径>` 拷回，并对照安装前记录的 SHA-256 校验，游戏因此回到**安装前的逐字节原样**
* 安装器新建的每个文件（DLL、ini，以及当你本来就没有松散 `chr\` 时的 `chr\c0000.chrbnd.dcx`）都会被删除
* 安装器新建的每个目录在清空后会被移除
* 最后 `tools\ds3tae.exe verify` 扫描 `chr\` 并报告还有哪些模型带假体 382/383，让「无残留」有据可查，而不是一句空话

```powershell
powershell -ExecutionPolicy Bypass -File restore.ps1 -DryRun       # 只报告，不改动
powershell -ExecutionPolicy Bypass -File restore.ps1 -AllowLegacy  # 1.0.4 及更早的安装
powershell -ExecutionPolicy Bypass -File restore.ps1 -KeepBackups  # 保留备份 + 清单
```

如果某个文件**已经**不是安装器放进去的那个（你换过，或别的 mod 改过），restore 会停下并告诉你，而不是覆盖别人的成果；`-Force` 可以强制完成。这时清单和备份会保留，以便重试。

**1.0.4 及更早的安装没有清单**，也没有角色模型的原始副本。它们随包的 `tools\ds3tae.exe` 甚至无法剥除：那个二进制早于 `stripdir` 子命令，只会回一行用法说明并以退出码 2 结束（这就是旧 `restore.ps1`「完成」了却什么都没还原的原因）。请改用本版本的 `tools\` 目录，运行 `restore.ps1 -AllowLegacy`。结构性剥除**不是**逐字节一致的：工具会移除假体并证明其余部分（骨骼、材质、网格、缓冲区布局）未动，但重新序列化 bnd 和重新压缩 DCX 总会产生略不同的文件。现在的新安装靠保留原始文件彻底避开了这一点。

备份会占磁盘空间：`.hsleft-backup\chr\` 副本和模型一样大（完整 165 个模型的 `chr\` 约 340 MB）。`install.ps1` 开始前会打印大小。这些备份由 `restore.ps1` 删除，只为让卸载能做到精确还原。

### 配置

`HideSheathedLeft.ini`（保存后一秒内生效，无需重启）：

| 键 | 默认 | 含义 |
|---|---|---|
| `HideLeftHang` | `1` | 隐藏收鞘的左手武器（双手持**右**手武器时触发） |
| `HideRightHang` | `1` | 镜像行为：隐藏收鞘的右手武器（双手持**左**手武器时触发） |
| `HideBothPaired` | `1` | 隐藏单手持成对武器时的备用模型，**左右手都** |
| `PairedFields` | `1,2,3` | 成对武器要隐藏哪些模型：`1` = 只隐藏刀刃（保留刀鞘），`none` = 不动成对武器 |
| `HidePoly` | `382` | 停放假体 id（`383` 备用，`-1` 复现 1.0.0 的瑕疵） |
| `IntervalSeconds` | `1` | 多久重新断言一次参数值 |
| `Rescan` | `1` | `0` = 停止周期性的地址空间重扫（见下方「性能」） |
| `ScanMapped` | `0` | `1` = 同时考虑 MEM_MAPPED 区域（诊断用） |
| `Probe` | `0` | `1` = 只观察（不写任何东西，日志写 `HideSheathedLeft.log`） |
| `ExtraMods` | *(空)* | 必须保持为空——在 1.15.0 上加载额外 DLL 会导致游戏崩溃 |

设 `HideLeftHang=0` 只恢复右手双手持姿势的原版行为；设 `HideRightHang=0` 则对左手双手持姿势做同样的事。当 `HideBothPaired` 不存在时，旧的 `HidePairedOffhand` 键仍会被读取（它原本只覆盖右手）。

### 性能

参数写入是廉价的部分：只在值真的不同时才发生，所以稳态下每秒只有寥寥几次内存读取。贵的是最初找到参数表——mod 会遍历进程的内存区域、复制它们的**常驻**页来查找表名。这只在启动时跑一次，之后只有当它持有的地址失效时才再跑（`Rescan=1`，默认值，让效果能自愈）。

* 1.0.1 还读**非常驻**页，把已换出的数据又拉回 RAM；DS3 会预先提交资源池，所以游戏工作集暴涨约 4 GB（实测 6007 MB，原版 1634 MB），卡顿也更严重。1.0.2 让扫描只读常驻页，之后每个版本（包括本版）都是只读常驻页。
* 如果看到卡顿，设 **`Rescan=0`**。这样启动扫描之后不再跑任何地址空间遍历，mod 就只剩那每秒几次读取。代价：如果引擎在会话中途重建了参数表，效果可能一直不生效，直到下次启动。
* `HideSheathedLeft.log` 记录了每次遍历的开销，例如 `scan: 4 table(s); read 0 MB resident, left 7615 MB untouched of 7619 MB seen`。如果设了 `Rescan=0` 仍卡顿、日志里也没有 scan 行，那掉帧就不是本 mod 造成的——无论如何请把日志报上来。

### 已知限制

* **NPC 也会隐藏武器。** 参数表是玩家和 NPC 共用的，而 mod 让停放假体对每个角色模型都有效，所以同姿势的 NPC 只是不画它收鞘的左手武器，而不是产生瑕疵。要只对玩家生效，需要 patch 引擎的挂载解析器（`exe+0xE31690` 选择器，唯一调用点 `exe+0xE35125`，访问器 `exe+0xE350D0`）。
* **偶发的「静默无效」。** 引擎在内存里保留了几份参数表副本，mod 只能改写它找到的那些，所以偶尔会漏掉引擎真正读的那份：武器留在背上（无瑕疵），直到下次启动。根因：引擎对每个角色**缓存**了已解析的挂载值，很少重读参数表。
* **黑三角 / 闪烁。** 那是 1.0.0 的瑕疵，意味着某个角色模型没有 382/383 假体，引擎于是建出退化挂载矩阵。一条命令验证：`tools\ds3tae.exe verify "<game>\chr" chrbnd "382,383"`——你想要的答案是 `scanned N file(s), N with an FLVER … files still carrying 382,383: N`。如果报的数更少，重跑 `install.cmd`（1.0.6 及之后会自行校验，不会虚报成功）。
* **1.0.4 及更早无法卸载。** 它们随包的 `tools\ds3tae.exe` 没有 `stripdir`，`restore.ps1` 还会在把每个角色模型都留在已 patch 状态的情况下报告成功。请用本版本的脚本和 `tools\`；见上方「卸载」。
* 别的 mod 替换过 `chr\` 里的文件后，重跑 `install.cmd`（或 `tools\patch-character-models.ps1`）——已 patch 的文件会跳过。

### 仓库结构

```
HideSheathedLeft.dll / .ini   mod 本体及其配置
xinput1_3.dll                 加载器外壳（转发系统 XInput）
install.cmd / install.ps1     安装（payload + 角色模型 patch）
restore.cmd / restore.ps1     卸载
tools\ds3tae.exe              模型 patch / 校验工具（+ SoulsFormats.dll）
tools\patch-character-models.ps1
docs\MANUAL-INSTALL.txt       逐步手动安装说明
```

### 版本沿革

当前版本：**1.0.6**。更早的版本不再分发：1.0.0 会产生瑕疵（黑三角、全屏闪烁），1.0.1 多占约 4 GB 内存，1.0.4 及更早无法卸载，1.0.5 可能让角色模型**保持未 patch**——`-Only` 把模型暂存在 `%TEMP%`，游戏在另一个盘时硬链接失败，回退到 Copy-Item 却 patch 了随后被删掉的临时副本，又没有任何东西检查结果，于是闪烁又回来了。1.0.6 把 patch 暂存放进 `chr\` 内，且 `install.ps1` 和 `patch-character-models.ps1` 现在都会打印并强制 `N of N character model(s) carry dummy 382/383`；mod 本身未变。对于 1.0.4 或更早的安装，请用本版本的 `tools\` 配合 `restore.ps1 -AllowLegacy`。

### 备注

* 本仓库**不附带任何游戏资产**：`tools\ds3tae.exe` 只给你自己的 `chr\*.chrbnd.dcx` 追加两个假体（并校验其余部分保持逐字节一致）。
* `install.ps1` 把即将覆盖的每个文件的逐字节副本保存在 `<game>\.hsleft-backup\`，并把这一切记录到 `<game>\.hsleft-manifest.json`，所以 `restore.ps1` 能把原始文件精确还原。`tools\ds3tae.exe stripdir` 仍作为没有清单的安装（`restore.ps1 -AllowLegacy`）的结构性回退方案。
* 内存：表扫描只读操作系统当前驻留的页，不会把游戏已换出的资源池拉回 RAM。`HideSheathedLeft.log` 会打印每次扫描的开销。
* 游戏目录里只能有一个 `xinput1_3.dll`：如果另一个 mod（比如按键提示 mod）已经占用了这个位置，安装器会把它改名为 `xinput1_3.dll.dkp-off` 并保留。两个 mod 不能同时生效。

### 许可

MIT——见 [`LICENSE`](LICENSE)。与 FromSoftware / Bandai Namco 无关；仅限单机离线使用。

---

## English

While you two-hand one hand's weapon, the **other hand's sheathed model is no longer drawn on your
back**. The behaviour is symmetric: two-hand the right weapon and the left item disappears; two-hand
the left weapon and the right item disappears. Works for anything hand-equippable: weapons, shields,
catalysts, bows, staves.

> Dark Souls III **1.15.0** (Steam, 64-bit). Local memory + model changes only. Online play has
> a server-side save sanity check — use it offline.

---

### What it does

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

### Requirements

* Dark Souls III 1.15.0 (Steam).
* A **loose-file setup** (`Game\chr\*.chrbnd.dcx` exists — the normal state after unpacking with
  UXM, which model mods require). The bundled patcher edits those files in place.
* Windows PowerShell (built in). .NET 8/10 runtime is only needed if you rebuild the tools.

---

### Install

1. Close the game.
2. Double-click **`install.cmd`** (or run `powershell -ExecutionPolicy Bypass -File install.ps1`).

It copies the payload into the game folder and then appends dummy 382/383 to every
`chr\*.chrbnd.dcx` (each file is verified before writing; files that already have the dummies are
skipped). Manual, step-by-step install: [`docs/MANUAL-INSTALL.txt`](docs/MANUAL-INSTALL.txt).

Check the state at any time:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Status
```

#### Uninstall

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

### Configuration

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

### Performance

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

### Known limitations

* **NPCs hide the item too.** The parameter table is shared between the player and NPCs, and
  the mod makes the parking dummy valid for every character model, so an NPC in the same stance
  simply does not draw its sheathed left item instead of producing artefacts. Making it
  player-only requires patching the engine's attach resolver (`exe+0xE31690` selector, single call
  site `exe+0xE35125`, accessor `exe+0xE350D0`).
* **Rare "silent no-op".** The engine keeps several copies of the parameter table in memory and
  the mod can only rewrite the ones it finds, so occasionally the copy the engine actually reads
  is missed: the item stays on your back (no artefacts) until the next launch. Root cause: the
  engine **caches** the resolved attach values per character and rarely re-reads the table.
* **Black triangles / flicker.** That is the 1.0.0 artefact and it means a character model has no
  dummy 382/383, so the engine builds a degenerate attach matrix. Prove it in one command:
  `tools\ds3tae.exe verify "<game>\chr" chrbnd "382,383"` — the answer you want is
  `scanned N file(s), N with an FLVER … files still carrying 382,383: N`. If it reports fewer,
  run `install.cmd` again (1.0.6 and later verify this themselves and refuse to claim success).
* **1.0.4 and earlier cannot uninstall.** Their packaged `tools\ds3tae.exe` has no `stripdir`, and
  their `restore.ps1` reported success while leaving every character model patched. Use this
  version's scripts and `tools\`; see the Uninstall section above.
* After another mod replaces files in `chr\`, run `install.cmd` (or
  `tools\patch-character-models.ps1`) again — already-patched files are skipped.

---

### Repository layout

```
HideSheathedLeft.dll / .ini   mod core and its configuration
xinput1_3.dll                 loader shell (forwards the system XInput)
install.cmd / install.ps1     install (payload + character-model patch)
restore.cmd / restore.ps1     uninstall
tools\ds3tae.exe              model patch / validation tool (+ SoulsFormats.dll)
tools\patch-character-models.ps1
docs\MANUAL-INSTALL.txt       step-by-step manual install
```

### Version lineage

Current build: **1.0.6**. Earlier builds are no longer distributed: 1.0.0 drew artefacts (black
triangles, full-screen flicker), 1.0.1 used ~4 GB more RAM, 1.0.4 and older cannot uninstall, and
1.0.5 could leave the character models **unpatched** — `-Only` staged the models in `%TEMP%`, the
hardlink failed whenever the game sat on another drive, the copy fallback patched a temp copy that
was then deleted, and nothing checked the result, so the flicker came back. 1.0.6 stages the patch
inside `chr\` and both `install.ps1` and `patch-character-models.ps1` now print and enforce
`N of N character model(s) carry dummy 382/383`; the mod itself is unchanged.
For an installation made by 1.0.4 or older, use this version's `tools\` with
`restore.ps1 -AllowLegacy`.

### Notes

* This repository ships **no game assets**: `tools\ds3tae.exe` only appends two dummies to
  **your own** `chr\*.chrbnd.dcx` files (and verifies that everything else stays byte-identical).
* `install.ps1` keeps a byte-exact copy of every file it is about to overwrite in
  `<game>\.hsleft-backup\` and records all of it in `<game>\.hsleft-manifest.json`, so
  `restore.ps1` can put the originals back exactly.  `tools\ds3tae.exe stripdir` remains as the
  structural fallback for installations that have no manifest (`restore.ps1 -AllowLegacy`).
* Memory: the table scan only reads pages the OS currently holds resident, so it cannot pull the
  game's paged-out resource pools back into RAM. `HideSheathedLeft.log` prints what each scan cost.
* Only one `xinput1_3.dll` can live in the game folder: if another mod (e.g. a key-prompt mod)
  already owns that slot, the installer renames it to `xinput1_3.dll.dkp-off` and keeps it.
  The two mods cannot be active at the same time.

### License

MIT — see [`LICENSE`](LICENSE). Not affiliated with FromSoftware or Bandai Namco; single-player,
offline use only.
