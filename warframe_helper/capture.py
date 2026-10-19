"""Bildschirmfotos und Infos zum Warframe-Fenster, für Windows und Linux.

- Hyprland (Wayland): `hyprctl` für Fenster und Monitore, `grim` für Fotos
- Windows: Win32-API für das Vordergrundfenster, `mss` für Fotos
- X11 und andere: `mss`, ohne Fenstererkennung (es wird der gewählte Monitor fotografiert)

Es wird nur der Bildschirm fotografiert, das Spiel selbst wird nicht angefasst.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

import numpy as np

WARFRAME_CLASSES = ("steam_app_230410", "warframe.x64.exe")
WARFRAME_TITLE = "Warframe"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Monitor:
    name: str
    rect: Rect


@dataclass(frozen=True)
class GameWindow:
    rect: Rect
    focused: bool


def _run(cmd: list[str]) -> bytes | None:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=3, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_ppm(data: bytes) -> np.ndarray:
    # Kopf: "P6\n<breite> <höhe>\n<max>\n", danach RGB-Bytes
    parts = data.split(maxsplit=4)
    if len(parts) < 5 or parts[0] != b"P6":
        raise ValueError("kein PPM-Bild")
    w, h = int(parts[1]), int(parts[2])
    pixels = data[len(data) - w * h * 3 :]
    return np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 3)


class Backend:
    name = "?"

    def monitors(self) -> list[Monitor]:
        raise NotImplementedError

    def game_window(self) -> GameWindow | None:
        """Warframe-Fenster, falls erkennbar. None = unbekannt."""
        return None

    def grab(self, rect: Rect) -> np.ndarray:
        """RGB-Bild des Bereichs als numpy-Array (Höhe, Breite, 3)."""
        raise NotImplementedError


class HyprlandBackend(Backend):
    name = "Hyprland"

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and bool(shutil.which("grim"))

    def monitors(self) -> list[Monitor]:
        raw = _run(["hyprctl", "monitors", "-j"])
        if not raw:
            return []
        result = []
        for m in json.loads(raw):
            scale = m.get("scale", 1) or 1
            w, h = round(m["width"] / scale), round(m["height"] / scale)
            if m.get("transform", 0) % 2:
                w, h = h, w
            result.append(Monitor(m["name"], Rect(m["x"], m["y"], w, h)))
        return result

    def game_window(self) -> GameWindow | None:
        raw = _run(["hyprctl", "clients", "-j"])
        if not raw:
            return None
        active = json.loads(_run(["hyprctl", "activewindow", "-j"]) or b"{}") or {}
        for c in json.loads(raw):
            if c.get("class", "").lower() in WARFRAME_CLASSES or c.get("title") == WARFRAME_TITLE:
                rect = Rect(c["at"][0], c["at"][1], c["size"][0], c["size"][1])
                return GameWindow(rect, active.get("address") == c.get("address"))
        return None

    def grab(self, rect: Rect) -> np.ndarray:
        data = _run(["grim", "-t", "ppm", "-g", f"{rect.x},{rect.y} {rect.w}x{rect.h}", "-"])
        if not data:
            raise RuntimeError("grim konnte kein Bild machen")
        return _parse_ppm(data)


class MssBackend(Backend):
    name = "mss"

    def __init__(self):
        import mss

        self._mss_module = mss
        self._local = None

    def _sct(self):
        # mss-Objekte sind an den Thread gebunden, der sie erzeugt hat
        import threading

        if self._local is None:
            self._local = threading.local()
        if not hasattr(self._local, "sct"):
            self._local.sct = self._mss_module.mss()
        return self._local.sct

    def monitors(self) -> list[Monitor]:
        mons = self._sct().monitors[1:]  # [0] ist der ganze Desktop
        return [
            Monitor(f"Monitor {i + 1} ({m['width']}×{m['height']})", Rect(m["left"], m["top"], m["width"], m["height"]))
            for i, m in enumerate(mons)
        ]

    def game_window(self) -> GameWindow | None:
        if sys.platform != "win32":
            return None
        return _win32_game_window()

    def grab(self, rect: Rect) -> np.ndarray:
        shot = self._sct().grab({"left": rect.x, "top": rect.y, "width": rect.w, "height": rect.h})
        # BGRA -> RGB
        return np.asarray(shot)[:, :, 2::-1].copy()


def _win32_game_window() -> GameWindow | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WARFRAME_TITLE)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    # Client-Bereich in Bildschirmkoordinaten (ohne Rahmen und Titelleiste)
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    focused = user32.GetForegroundWindow() == hwnd
    return GameWindow(Rect(origin.x, origin.y, rect.right, rect.bottom), focused)


_backend: Backend | None = None


def backend() -> Backend:
    global _backend
    if _backend is None:
        if sys.platform.startswith("linux") and HyprlandBackend.available():
            _backend = HyprlandBackend()
        else:
            _backend = MssBackend()
    return _backend
