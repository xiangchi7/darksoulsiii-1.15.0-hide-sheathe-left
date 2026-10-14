# HideSheathedLeft (Dark Souls III 1.15.0)

双持右手武器时，**不再把左手道具（武器 / 盾 / 法杖 / 弓…）的模型挂在背上**。
Hide the left-hand item's sheathed model instead of letting it hang on your back
while you two-hand the right-hand weapon.

> 支持 Dark Souls III **1.15.0**（Steam，64 位）。仅本地内存/模型改动，联机有服务端存档检查风险，建议离线使用。

---

## 效果 / What it does

| 状态 | 原版 | 本 mod |
|---|---|---|
| 右手武器**双持**、左手有道具 | 左手道具挂在背上 | 左手道具**不可见** |
| 左手道具**正在使用**（持盾/挥砍） | 正常显示 | **正常显示**（不受影响） |
| 右手拿**成对武器**、单持 | 副手模型挂在身上 | 副手模型**不可见**（`PairedFields` 可只隐藏刀刃、保留刀鞘） |

实现方式（1.0.1）：把 `WepAbsorpPosParam` 的 `leftHang_0..3` / `right_1..3` 指向一个
**停在角色正下方 1000 米的"停放挂点"**（382/383），模型被挂到那里后不在视锥内，因此不可见；
挂点被追加到**每个角色模型**里，所以任何角色解析它都不会得到无效矩阵
（1.0.0 直接写无效挂点 `-1`，会触发黑三角 + 全屏闪烁）。

---

## 安装 / Install

**要求**：游戏为"散装文件"（loose files）状态，即 `Game\chr\` 下有 `*.chrbnd.dcx`
（用 UXM 解包过，模型类 mod 的常规状态）。补丁器需要在你的游戏文件上追加两个挂点。

### 一键安装（推荐）

1. 关闭游戏；
2. 双击 `一键安装.cmd`（或 `powershell -ExecutionPolicy Bypass -File install.ps1`）；
3. 它会：复制 4 个文件到游戏目录 → 给 `chr\*.chrbnd.dcx` 里每个模型追加挂点 382/383
   （逐文件校验，已有则跳过）。

查看状态：`install.ps1 -Status`（会顺带校验模型补丁是否完整）。

### 手动安装

见 [`docs/手动安装说明.txt`](docs/手动安装说明.txt)。

### 卸载 / 还原

双击 `一键还原.cmd`（或 `restore.ps1`）。若想同时撤销模型补丁：

```powershell
tools\ds3tae.exe stripdir "<游戏>\chr" INPLACE "382,383" "chrbnd"
```

---

## 配置 / Configuration

`HideSheathedLeft.ini`（存盘后 1 秒内生效，无需重启）：

| 键 | 默认 | 说明 |
|---|---|---|
| `HideLeftHang` | `1` | 核心效果：隐藏收起状态的左手道具 |
| `HidePairedOffhand` | `1` | 成对武器单持时隐藏副手模型 |
| `PairedFields` | `1,2,3` | 隐藏右侧哪些模型；`1` 只藏副手刀刃、保留刀鞘，`none` 不动右手模型 |
| `HidePoly` | `382` | 停放挂点 id（`383` 备用；`-1` 复现旧的黑三角 bug） |
| `IntervalSeconds` | `1` | 参数重申间隔 |
| `Probe` | `0` | `1` = 只观察不写数据（诊断，输出到 `HideSheathedLeft.log`） |
| `ExtraMods` | 空 | 必须留空（1.15.0 下再挂别的 DLL 会让游戏启动即崩） |

---

## 已知限制 / Known limitations

* **NPC 也会一起隐藏**那件道具：参数表 PC/NPC 共用，1.0.1 的做法是让所有角色模型都拥有停放挂点，
  于是 NPC 也不显示而不是产生黑三角/穿模。要做到"只影响玩家"，需要改引擎的挂点解析
  （见 `docs/技术说明.md` 里已定位到的代码坐标：选择器 `exe+0xE31690`、唯一调用点 `exe+0xE35125`、
  访问器 `exe+0xE350D0`），属于修改游戏代码，本版本未采用。
* **偶发"静默失效"**：游戏内存里存在多份参数表副本，mod 只能打到扫描到的那几份；
  表现为道具照旧挂在背上（不会出黑三角），重启游戏通常即可恢复。根因是引擎把解析结果
  **缓存在角色结构里**，运行时很少读共享参数表。
* 若其它 mod 覆盖了 `chr\*.chrbnd.dcx`，需要重跑一次补丁器（`一键安装.cmd` 会跳过已打好的文件）。

---

## 从源码构建 / Build from source

需要 Visual Studio Build Tools（MSVC，x64）与 .NET SDK：

```powershell
# mod 本体 + 加载器壳 -> dist\
powershell -ExecutionPolicy Bypass -File src\build.ps1

# 模型补丁/校验工具 -> validator\bin\Release\net10.0\ds3tae.exe
dotnet build validator\validator.csproj -c Release
```

* `src\HideSheathedLeft.cpp` — mod 本体（定位参数表、写入停放挂点、可选探针）
* `src\xinput1_3_proxy.cpp` / `.def` — 加载器壳（转发 XInput 1..8 导出函数）
* `validator\Main.cs` — `ds3tae` 工具：`parkdir` / `stripdir` / `scanid` / `flverdiff` / `dummies` …

---

## 仓库内容 / Repository layout

```
HideSheathedLeft.dll       mod 本体（已编译）
HideSheathedLeft.ini       配置
xinput1_3.dll              加载器壳（转发系统 XInput）
install.ps1 / 一键安装.cmd  安装（含模型补丁）
restore.ps1 / 一键还原.cmd  还原
tools\ds3tae.exe           模型补丁 / 校验工具
tools\patch-character-models.ps1  只跑模型补丁
docs\手动安装说明.txt        手动安装（纯复制文件）
docs\技术说明.md            机制说明、验证证据、逆向结论（挂点解析代码坐标）
research\                  调查过程中用到的脚本与数据（Python）
src\ validator\            源码
```

---

## 说明 / Notes

* 本仓库**不附带任何游戏原始资源**：`tools\ds3tae.exe` 只是在**你自己的** `chr\*.chrbnd.dcx`
  末尾追加两个挂点（并校验其余结构完全不变），模型文件请在本地生成。
* 安装脚本会把被覆盖的文件备份成 `*.vanilla-backup`，可随时还原。
* 与其它 DLL 加载器（例如按键提示 mod 的 `xinput1_3.dll`）**只能二选一**；
  安装时会把对方改名保留为 `xinput1_3.dll.dkp-off`。

## License

MIT（见 `LICENSE`）。与 FromSoftware / Bandai Namco 无关，仅供单机离线使用。
