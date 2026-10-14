#!/usr/bin/env python3
"""One-off: keep the repo docs in sync with the -1000 m / 382+383 model patch."""

import io
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))       # ds3-hide-sheathed
REPO = os.path.join(os.path.dirname(WS), "HideSheathedLeft")
README = os.path.join(REPO, "README.md")
CHANGELOG = os.path.join(REPO, "CHANGELOG.md")

README_REPS = [
    ("parks 300 m below", "parks 1000 m below"),
    ("`(0, -300, 0)`, 300 m below the character", "`(0, -1000, 0)`, 1000 m below the character"),
]

CHANGELOG_REPS = [
    ("so `382` / `94` / a vanilla sheath id", "so `382` / `383` / a vanilla sheath id"),
]


def patch(path, reps):
    text = io.open(path, encoding="utf-8").read()
    before = text
    for old, new in reps:
        if old not in text:
            print("  MISS %s: %r" % (os.path.basename(path), old[:50]))
        text = text.replace(old, new)
    if text != before:
        io.open(path, "w", encoding="utf-8", newline="").write(text)
    print("  %s: %s" % (os.path.basename(path), "changed" if text != before else "unchanged"))


if __name__ == "__main__":
    patch(README, README_REPS)
    patch(CHANGELOG, CHANGELOG_REPS)
