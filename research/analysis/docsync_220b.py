#!/usr/bin/env python3
"""Second pass: the two remaining 382-default mentions in the parking README."""

import io
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARK = os.path.join(WS, "parking", "README.md")

REPS = [
    ("* SoulsFormats 结构对比：384 个挂点（原版 382），**原版 382 条一条都没动**（工具报 `dummy entries changed: 0`），\n     骨骼表摘要完全一致，包内**只有** `c0000.flver` 这一个 entry 变化；",
     "* SoulsFormats 结构对比：384 个挂点（原版 382）；改动**只有两处** —— 220 被移到 `(0,-1000,0)`、末尾新增 382/383；\n     骨骼表摘要完全一致，包内**只有** `c0000.flver` 这一个 entry 变化；"),
    ("2. `HideSheathedLeft.dll`：`0xFFFF` 变成 ini 里的 `HidePoly`（默认 `382`，可切 `383`，`-1` 回退旧行为）；",
     "2. `HideSheathedLeft.dll`：`0xFFFF` 变成 ini 里的 `HidePoly`（默认 `220`，可切 `382`/`383`，`-1` 回退旧行为）；"),
]


def main():
    text = io.open(PARK, encoding="utf-8").read()
    before = text
    for old, new in REPS:
        if old not in text:
            print("MISS: %r" % old[:60])
        text = text.replace(old, new, 1)
    if text != before:
        io.open(PARK, "w", encoding="utf-8", newline="").write(text)
    print("parking README:", "changed" if text != before else "unchanged")


if __name__ == "__main__":
    main()
