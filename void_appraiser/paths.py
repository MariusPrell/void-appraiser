"""Storage locations: cache, settings, and finding the Warframe log (EE.log)."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

APP_NAME = "void-appraiser"
# Up to version 0.7 the program was called "Warframe Helper"; its folders are taken over
OLD_APP_NAME = "warframe-helper"
WARFRAME_STEAM_ID = "230410"
LOG_IN_PREFIX = Path("pfx/drive_c/users/steamuser/AppData/Local/Warframe/EE.log")


def _app_dir(base: Path) -> Path:
    """Folder of the program; on first start the old folder is renamed."""
    path = base / APP_NAME
    old = base / OLD_APP_NAME
    if not path.exists() and old.is_dir():
        try:
            shutil.move(str(old), str(path))
        except OSError:
            pass  # then without the old data
    return path


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = _app_dir(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return _app_dir(base) / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _steam_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",  # Flatpak
    ]


def _steam_libraries() -> list[Path]:
    """All Steam libraries from libraryfolders.vdf (Linux)."""
    libs: list[Path] = []
    for root in _steam_roots():
        vdf = root / "steamapps/libraryfolders.vdf"
        if not vdf.is_file():
            continue
        libs.append(root)
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        libs += [Path(p) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    # Keep the order, remove duplicates
    seen, result = set(), []
    for lib in libs:
        key = lib.resolve() if lib.exists() else lib
        if key not in seen:
            seen.add(key)
            result.append(lib)
    return result


def find_log_candidates() -> list[Path]:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return [Path(local) / "Warframe/EE.log"] if local else []
    return [
        lib / "steamapps/compatdata" / WARFRAME_STEAM_ID / LOG_IN_PREFIX
        for lib in _steam_libraries()
    ]


def find_log(cfg: dict | None = None) -> Path | None:
    """Log path: from the settings first, otherwise searched automatically."""
    cfg = cfg if cfg is not None else load_config()
    if cfg.get("log_path"):
        return Path(cfg["log_path"])
    existing = [p for p in find_log_candidates() if p.is_file()]
    if not existing:
        return None
    # With several matches, take the most recently written log
    return max(existing, key=lambda p: p.stat().st_mtime)
