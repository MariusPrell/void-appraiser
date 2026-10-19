"""Gibt den Abschnitt einer Version aus CHANGELOG.md aus (für den Release-Text auf GitHub).

Aufruf: python packaging/release_notes.py 0.8.0 > notes.md
"""

import sys
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"


def section(version: str) -> str:
    lines, inside = [], False
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == version
            continue
        if inside:
            lines.append(line)
    text = "\n".join(lines).strip()
    return text or f"Version {version}"


if __name__ == "__main__":
    version = sys.argv[1].removeprefix("v")
    print(section(version))
    print("\n**Installation:** siehe [README](https://github.com/MariusPrell/void-appraiser#installation).")
