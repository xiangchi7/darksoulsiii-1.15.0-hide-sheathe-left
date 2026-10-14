#!/usr/bin/env python3
"""Sync docs with the 'append the parking dummy to EVERY character model' design."""

import io
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(WS)
PARK = os.path.join(WS, "parking", "README.md")
README = os.path.join(ROOT, "HideSheathedLeft", "README.md")
CHANGELOG = os.path.join(ROOT, "HideSheathedLeft", "CHANGELOG.md")

REPS = {
    PARK: [
        ("| 怎么写参数 | 把 `leftHang_0..3`（成对武器还有 `right_1..3`）写成 `0xFFFF`（= 无效挂点） | 默认写 **220**：一个**所有角色模型几乎都有**、且**没有任何参数字段引用**的挂点；玩家模型里把 220 挪到正下方 1000 米（`382`/`383` 作为备选，ini 里可实时切换） |",
         "| 怎么写参数 | 把 `leftHang_0..3`（成对武器还有 `right_1..3`）写成 `0xFFFF`（= 无效挂点） | 默认写 **382**：模型补丁给**每一个角色模型**都追加了这个挂点（在各自正下方 1000 米），因此玩家和 NPC 都会把这件道具放到看不见的地方（`383` 备用，ini 可切换） |"),
        ("""1. `chr\\c0000.chrbnd.dcx`：在玩家模型 `c0000.flver` 里
   ① 把**挂点 220** 从它原来的位置（身体中线内部，如 `(0, 1.29, -0.08)`）挪到 `(0, -1000, 0)`；
   ② 末尾**新增两个**挂点 `382` / `383`（都在 `(0, -1000, 0)`）作为备选。
   为什么主用 220：它是**"空闲挂点"**（91 行参数里没有任何字段引用它），而且 **165 个角色模型里有 160 个
   都有它**、位置固定在各自的**身体中线内部**。于是：
   * **玩家**：参数指向 220，而 220 在玩家模型里已被挪到 1000 米下 → 收起道具看不见；
   * **NPC**：它们的模型里 220 还在原位（体内），所以即使敌人进入同一姿态，也只是把这件道具画在
     **自己身体内部**——**不会再出现黑三角/闪烁**（这正是对"NPC 通道"的解法）。""",
         """1. `chr\\*.chrbnd.dcx`：给**全部 165 个角色模型**各追加两个挂点 `382` / `383`
   （父骨骼 `0`、位置 `(0, -1000, 0)`），**不改动任何原版挂点** —— 工具在写入前会先验证
   骨骼表 / 材质 / 网格 / 缓冲布局完全没变、原挂点条目一条没动，否则那个文件原样保留。
   于是参数指向 382 时：
   * **玩家**：道具被放到 1000 米下方 → 看不见（与以前一致）；
   * **NPC**：同样解析到有效挂点 → 道具也在它下方 1000 米处 → **看不见**，
     **不会穿模、不会被缩放变形、也不会出现黑三角**（这就是对"NPC 通道"的解法）。"""),
        ("* SoulsFormats 结构对比：384 个挂点（原版 382）；改动**只有两处** —— 220 被移到 `(0,-1000,0)`、末尾新增 382/383；\n     骨骼表摘要完全一致，包内**只有** `c0000.flver` 这一个 entry 变化；",
         "* SoulsFormats 结构对比（以玩家模型为例）：384 个挂点（原版 382），改动**只有**末尾新增 382/383，\n     原版 382 条一条没动（工具报 `dummy entries changed: 0`），骨骼表摘要完全一致，包内**只有** `c0000.flver` 变化；"),
        ("     **没有任何部件或其它角色占用 382 / 383**（部件里最大挂点 id 890）；",
         "     **没有任何部件占用 382 / 383**（部件里最大挂点 id 890）；随后给 165 个角色模型全部追加了这两个挂点\n     （`patched=164 already-had=1 failed=0`，328 个挂点；每个文件写入前都做了结构校验）；"),
        ("- **NPC 通道（已基本解决）**：参数表 PC/NPC 共用，所以默认用 **220**（160/165 个角色模型都有、且没有参数引用它）\n  —— 敌人即使进入\"右手双持 + 左手有道具\"，拿到的也是**有效挂点**，道具被画在它体内，**没有黑三角**。\n  残余：`c1000`（352 字节的占位）、`c2260`、`c6232`、`c6281`（2.5 KB）、`c6310` 这 5 个模型里没有 220，\n  理论上它们若进入该状态仍会走无效挂点；需要的话我可以给这 5 个模型各补一个 220（约 7 MB）。\n  如果要做到\"NPC 完全保持原版\"（而不是画在体内），仍然只有 hook 一条路。",
         "- **NPC 通道（已解决到\"不可见\"）**：所有角色模型都追加了 382/383，敌人进入同一姿态时道具同样被放到\n  1 公里下方 —— **没有黑三角、没有穿模、没有变形**。与 vanilla 的唯一差别是：那件道具也不会显示在 NPC 背上。\n  要做到\"NPC 完全保持原版（道具照旧挂背上）\"，只能 hook 挂点解析、把效果限定到玩家的 ChrAsm。\n- **模型补丁需要重跑**：换装/模型类 mod 若覆盖了 `chr\\*.chrbnd.dcx`，那 382/383 就没了（极端情况回到黑三角）。\n  本包 `tools\\` 里带了一个补丁器，改完模型后执行一次即可（见下）。"),
    ],
    README: [
        ("**parking dummy** (id `220`, a free dummy that 160 of the 165 character models already\nhave and that no parameter references) that the player-model patch in this release parks\n1000 m below",
         "**parking dummy** (`382`, appended to **every** character model by the model patch in this\nrelease) that is parked 1000 m below"),
        ("`(0, -1000, 0)` inside the player's own model, 1000 m below the character, so the model is attached with an",
         "`(0, -1000, 0)` in every character model, 1000 m below the character, so the model is attached with an"),
    ],
    CHANGELOG: [
        ("- The default parking dummy is now **`220`** instead of `382`.",
         "- The default parking dummy is **`382`**, and the model patch now appends it to **every**\n  character model (165 files) instead of only the player's. An earlier revision of this\n  entry used `220` (a free dummy 160/165 models already have, sitting inside the body) so\n  that NPCs would resolve a valid dummy; that was dropped because a real weapon is much\n  bigger than a torso and was visible poking out of it. With `382` appended everywhere,\n  both the player and any NPC that enters the stance get a valid dummy 1 km below, so the\n  sheathed item is simply never drawn: no black triangles, no clipping, no scaling. The\n  only difference from vanilla is that an NPC's sheathed left-hand item is hidden too.\n  Original entry follows.\n- (superseded) The default parking dummy was **`220`** instead of `382`."),
    ],
}


def patch(path, reps):
    text = io.open(path, encoding="utf-8").read()
    before = text
    for old, new in reps:
        if old not in text:
            print("  MISS %s: %r" % (os.path.basename(path), old[:55]))
            continue
        text = text.replace(old, new, 1)
    if text != before:
        io.open(path, "w", encoding="utf-8", newline="").write(text)
    print("  %s: %s" % (os.path.basename(path), "changed" if text != before else "unchanged"))


if __name__ == "__main__":
    for p, r in REPS.items():
        patch(p, r)
