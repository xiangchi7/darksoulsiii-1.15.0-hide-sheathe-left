#!/usr/bin/env python3
"""Sync the docs with the HidePoly=220 (NPC-safe) default."""

import io
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ds3-hide-sheathed
ROOT = os.path.dirname(WS)
PARK = os.path.join(WS, "parking", "README.md")
README = os.path.join(ROOT, "HideSheathedLeft", "README.md")
CHANGELOG = os.path.join(ROOT, "HideSheathedLeft", "CHANGELOG.md")

PARK_REPS = [
    ("| 怎么写参数 | 把 `leftHang_0..3`（成对武器还有 `right_1..3`）写成 `0xFFFF`（= 无效挂点） | 写成 **382** / **383**：两个**真实存在且停在远处**的挂点（ini 里可实时切换） |",
     "| 怎么写参数 | 把 `leftHang_0..3`（成对武器还有 `right_1..3`）写成 `0xFFFF`（= 无效挂点） | 默认写 **220**：一个**所有角色模型几乎都有**、且**没有任何参数字段引用**的挂点；玩家模型里把 220 挪到正下方 1000 米（`382`/`383` 作为备选，ini 里可实时切换） |"),
    ("""1. `chr\\c0000.chrbnd.dcx`：在玩家模型 `c0000.flver` 的挂点表末尾**新增两个**挂点
   （`ReferenceID = 382` / `383`，都等于它们在表里的下标；父骨骼 = 0 `Master`，位置 `(0, -1000, 0)`），
   **没有改动任何原版挂点**（这是相对上一版的改进：上一版挪动过一个测试挂点 `94`，本版改成再新增一个
   `383` 当备用，彻底避免"那个挂点被别处引用"的可能性）。
   `HidePoly` 想在哪个新挂点上面就在哪个上面，**换一个值只需改 ini，不用重装模型**。""",
     """1. `chr\\c0000.chrbnd.dcx`：在玩家模型 `c0000.flver` 里
   ① 把**挂点 220** 从它原来的位置（身体中线内部，如 `(0, 1.29, -0.08)`）挪到 `(0, -1000, 0)`；
   ② 末尾**新增两个**挂点 `382` / `383`（都在 `(0, -1000, 0)`）作为备选。
   为什么主用 220：它是**"空闲挂点"**（91 行参数里没有任何字段引用它），而且 **165 个角色模型里有 160 个
   都有它**、位置固定在各自的**身体中线内部**。于是：
   * **玩家**：参数指向 220，而 220 在玩家模型里已被挪到 1000 米下 → 收起道具看不见；
   * **NPC**：它们的模型里 220 还在原位（体内），所以即使敌人进入同一姿态，也只是把这件道具画在
     **自己身体内部**——**不会再出现黑三角/闪烁**（这正是对"NPC 通道"的解法）。"""),
    ("- **NPC 通道（唯一会重现老 bug 的逻辑通道，未解决）**：参数表 PC/NPC 共用，而扫描确认**其它角色模型都没有 382/383**。\n  所以若某个敌人进入\"右手双持 + 左手有道具\"的状态，它那一侧会拿到无效挂点 → 该 NPC 身上出现黑三角/闪烁。\n  彻底解决要 hook 挂点解析、把效果限定到玩家的 ChrAsm（见文末\"给你选的事\"）。",
     "- **NPC 通道（已基本解决）**：参数表 PC/NPC 共用，所以默认用 **220**（160/165 个角色模型都有、且没有参数引用它）\n  —— 敌人即使进入\"右手双持 + 左手有道具\"，拿到的也是**有效挂点**，道具被画在它体内，**没有黑三角**。\n  残余：`c1000`（352 字节的占位）、`c2260`、`c6232`、`c6281`（2.5 KB）、`c6310` 这 5 个模型里没有 220，\n  理论上它们若进入该状态仍会走无效挂点；需要的话我可以给这 5 个模型各补一个 220（约 7 MB）。\n  如果要做到\"NPC 完全保持原版\"（而不是画在体内），仍然只有 hook 一条路。"),
    ("| 又出现黑三角 / 全屏闪烁 | `382` 被当成**无效**挂点：说明引擎没把\"新增的挂点\"算进挂点表（或 `chr\\c0000.chrbnd.dcx` 没被加载） | **先试 `HidePoly=383`**（存盘，1 秒生效）→ 正常就说明是这一个 id 没被接受；仍黑三角则说明 `c0000.chrbnd.dcx`（或本包）没被加载，先确认游戏目录里的文件与备份（`-Status`），再看日志 |",
     "| 又出现黑三角 / 全屏闪烁 | 参数指向的挂点被判无效（默认 220 应该不会） | 先确认 `chr\\c0000.chrbnd.dcx` 被换成了本包的版本（`-Status`，应为 47 KB 左右）；再试 `HidePoly=382`（存盘，1 秒生效）看是否换成另一种表现 |"),
    ("| 盾跑到腰/背上（回到了可见位置） | 写值生效、但那个 id 指向的不是远处 | 试 `HidePoly=383`；再不行试 `45`/`46`（原版腰侧挂点）确认写值链路 |",
     "| 盾跑到腰/背上（回到了可见位置） | 参数没打到引擎在读的那份表（见下），或模型没换 | 先看日志有没有 `applied ...`；再用 `reference\\` 里的方法确认哪几份表被打到了 |"),
    ("config: HideLeftHang=1 HidePairedOffhand=1 PairedFields=111 IntervalSeconds=1 Log=1 HidePoly=382",
     "config: HideLeftHang=1 HidePairedOffhand=1 PairedFields=111 IntervalSeconds=1 Log=1 HidePoly=220"),
]

README_REPS = [
    ("**parking dummy** that the player-model patch in this release parks 1000 m below",
     "**parking dummy** (id `220`, a free dummy that 160 of the 165 character models already\nhave and that no parameter references) that the player-model patch in this release parks\n1000 m below"),
    ("`(0, -1000, 0)`, 1000 m below the character, so the model is attached with an",
     "`(0, -1000, 0)` inside the player's own model, 1000 m below the character, so the model is attached with an"),
]

CHANGELOG_REPS = [
    ("### Changed\n",
     """### Changed

- The default parking dummy is now **`220`** instead of `382`. Dummy `220` is not
  referenced by any `WepAbsorpPosParam` field and exists in 160 of the 165
  character models, sitting on each model's centre line (inside the body). The
  player's model has it parked 1000 m below, so the player is hidden exactly as
  before; an NPC that enters the same stance now resolves a **valid** dummy and
  simply draws its sheathed item inside its own body instead of getting the
  degenerate-matrix artifacts. `382` / `383` (dummies appended to the player's
  model) remain selectable through `HidePoly`.
"""),
]


def patch(path, reps):
    text = io.open(path, encoding="utf-8").read()
    before = text
    for old, new in reps:
        if old not in text:
            print("  MISS %s: %r" % (os.path.basename(path), old[:60]))
        text = text.replace(old, new, 1)
    if text != before:
        io.open(path, "w", encoding="utf-8", newline="").write(text)
    print("  %s: %s" % (os.path.basename(path), "changed" if text != before else "unchanged"))


if __name__ == "__main__":
    for p, r in ((PARK, PARK_REPS), (README, README_REPS), (CHANGELOG, CHANGELOG_REPS)):
        patch(p, r)
