"""Generates THIRD-PARTY-LICENSES.txt for the built packages.

Walks all runtime dependencies starting from "void-appraiser" (without extras
like pytest) and collects name, version, license, homepage and the bundled
license texts.

Usage: python packaging/licenses.py OUTPUT_FILE
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

ROOT = "void-appraiser"
LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)

# Packages without their own license files: manual note
EXTRA_NOTES = {
    "pyside6": (
        "Qt for Python (PySide6, shiboken6) and the included Qt libraries are licensed under the "
        "GNU Lesser General Public License v3 (LGPL-3.0).\n"
        "License text: https://www.gnu.org/licenses/lgpl-3.0.txt\n"
        "Source code: https://code.qt.io/ and https://download.qt.io/official_releases/QtForPython/\n"
        "The Qt libraries are separate files in the program folder and can be replaced."
    ),
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(dist) -> list[str]:
    names = []
    for req in dist.requires or []:
        # Only dependencies without an "extra" marker; platform markers are kept
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
            continue  # e.g. a platform dependency not installed here
        seen[key] = dist
        todo.extend(_requirements(dist))
    seen.pop(_norm(ROOT), None)
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def render(dists: list) -> str:
    out = [
        "Void Appraiser – licenses of bundled third-party software",
        "=" * 60,
        "",
        "Python itself is licensed under the Python Software Foundation License (https://docs.python.org/3/license.html).",
        "",
    ]
    # OCR models (PaddleOCR, Apache-2.0) are bundled as files, not as a Python package
    models = Path(__file__).parent.parent / "void_appraiser" / "models"
    for name in ("README.md", "MODEL_LICENSES.md", "LICENSE-Apache-2.0.txt"):
        path = models / name
        if path.is_file():
            out += ["-" * 60, f"OCR models: {name}", "", path.read_text(encoding="utf-8").strip(), ""]
    for dist in dists:
        meta = dist.metadata
        license_name = meta.get("License-Expression") or ""
        if not license_name:
            classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
            short = (meta.get("License") or "").strip().splitlines()
            license_name = ", ".join(classifiers) or (short[0] if short else "see license text")
        homepage = meta.get("Home-page") or ""
        for url in meta.get_all("Project-URL") or []:
            homepage = homepage or url.split(",", 1)[-1].strip()
        out += ["-" * 60, f"{meta['Name']} {dist.version}", f"License: {license_name}"]
        if homepage:
            out.append(f"Homepage: {homepage}")
        note = EXTRA_NOTES.get(_norm(meta["Name"]))
        if note:
            out += ["", note]
        for file in dist.files or []:
            # License texts from the package metadata (*.dist-info, also dist-info/licenses/)
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
    print(f"{len(dists)} packages -> {target}")
