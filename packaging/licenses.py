"""Erzeugt THIRD-PARTY-LICENSES.txt für die fertigen Pakete.

Geht von "warframe-helper" aus alle Laufzeit-Abhängigkeiten durch (ohne
Extras wie pytest) und sammelt Name, Version, Lizenz, Webseite und die
mitgelieferten Lizenztexte.

Aufruf: python packaging/licenses.py AUSGABEDATEI
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

ROOT = "warframe-helper"
LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)

# Pakete ohne eigene Lizenzdateien: Hinweis von Hand
EXTRA_NOTES = {
    "pyside6": (
        "Qt for Python (PySide6, shiboken6) und die enthaltenen Qt-Bibliotheken stehen unter der "
        "GNU Lesser General Public License v3 (LGPL-3.0).\n"
        "Lizenztext: https://www.gnu.org/licenses/lgpl-3.0.txt\n"
        "Quellcode: https://code.qt.io/ und https://download.qt.io/official_releases/QtForPython/\n"
        "Die Qt-Bibliotheken liegen als eigene Dateien im Programmordner und können ausgetauscht werden."
    ),
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(dist) -> list[str]:
    names = []
    for req in dist.requires or []:
        # Nur Abhängigkeiten ohne "extra"-Bedingung, Plattform-Bedingungen bleiben drin
        if "extra ==" in req.replace("extra==", "extra =="):
            continue
        names.append(re.split(r"[\s;<>=!~\[(]", req, maxsplit=1)[0])
    return names


def collect() -> list:
    seen: dict[str, object] = {}
    todo = [ROOT]
    while todo:
        name = todo.pop()
        key = _norm(name)
        if key in seen:
            continue
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue  # z. B. Plattform-Abhängigkeit, die hier nicht installiert ist
        seen[key] = dist
        todo.extend(_requirements(dist))
    seen.pop(_norm(ROOT), None)
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def render(dists: list) -> str:
    out = [
        "Warframe Helper – Lizenzen der mitgelieferten Fremdsoftware",
        "=" * 60,
        "",
        "Python selbst steht unter der Python Software Foundation License (https://docs.python.org/3/license.html).",
        "",
    ]
    # OCR-Modelle (PaddleOCR, Apache-2.0) liegen als Dateien bei, nicht als Python-Paket
    models = Path(__file__).parent.parent / "warframe_helper" / "models"
    for name in ("README.md", "MODEL_LICENSES.md", "LICENSE-Apache-2.0.txt"):
        path = models / name
        if path.is_file():
            out += ["-" * 60, f"OCR-Modelle: {name}", "", path.read_text(encoding="utf-8").strip(), ""]
    for dist in dists:
        meta = dist.metadata
        license_name = meta.get("License-Expression") or ""
        if not license_name:
            classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
            short = (meta.get("License") or "").strip().splitlines()
            license_name = ", ".join(classifiers) or (short[0] if short else "siehe Lizenztext")
        homepage = meta.get("Home-page") or ""
        for url in meta.get_all("Project-URL") or []:
            homepage = homepage or url.split(",", 1)[-1].strip()
        out += ["-" * 60, f"{meta['Name']} {dist.version}", f"Lizenz: {license_name}"]
        if homepage:
            out.append(f"Webseite: {homepage}")
        note = EXTRA_NOTES.get(_norm(meta["Name"]))
        if note:
            out += ["", note]
        for file in dist.files or []:
            # Lizenztexte aus den Paket-Metadaten (*.dist-info, auch dist-info/licenses/)
            if ".dist-info" in str(file) and (LICENSE_FILE.search(file.name) or file.parent.name == "licenses"):
                try:
                    text = file.locate().read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    continue
                if text:
                    out += ["", f"--- {file.name} ---", text]
        out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "THIRD-PARTY-LICENSES.txt")
    dists = collect()
    target.write_text(render(dists), encoding="utf-8")
    print(f"{len(dists)} Pakete -> {target}")
