"""Steuerung eigener Fenster unter Hyprland (für das Overlay).

Wayland-Programme dürfen ihre Fenster nicht selbst platzieren, deshalb
geht das über `hyprctl dispatch`. Angefasst werden nur die eigenen Overlay-
Fenster, keine Einstellungen von Hyprland.

Hyprland ab 0.55 mit Lua-Konfiguration erwartet Lua-Aufrufe
(`hl.dsp.window.float({...})`), ältere Versionen die klassische Syntax.
Beides wird unterstützt; die klassische ist ungetestet.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass


def _hyprctl(*args: str) -> str:
    try:
        out = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=3)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def clients() -> list[dict]:
    try:
        return json.loads(_hyprctl("clients", "-j") or "[]")
    except ValueError:
        return []


def find_window(title: str) -> str | None:
    for c in clients():
        if c.get("title") == title:
            return c.get("address")
    return None


def active_window() -> str | None:
    try:
        return json.loads(_hyprctl("activewindow", "-j") or "{}").get("address")
    except ValueError:
        return None


@dataclass
class _Syntax:
    lua: bool | None = None


_syntax = _Syntax()


def _dispatch(lua: str, classic: list[str]) -> bool:
    if _syntax.lua is not False:
        result = _hyprctl("dispatch", lua)
        if result == "ok":
            _syntax.lua = True
            return True
        if _syntax.lua is True:
            return False
    result = _hyprctl("dispatch", *classic)
    if result == "ok":
        _syntax.lua = False
        return True
    return False


def _w(address: str) -> str:
    return f'window = "address:{address}"'


def set_prop(address: str, prop: str, value: str, classic_prop: str) -> None:
    _dispatch(
        f'hl.dsp.window.set_prop({{ {_w(address)}, prop = "{prop}", value = "{value}" }})',
        ["setprop", f"address:{address}", classic_prop, value],
    )


def setup_overlay(address: str) -> None:
    """Schwebend, ohne Rahmen, Schatten, Animation und ohne Fokus."""
    _dispatch(f'hl.dsp.window.float({{ action = "enable", {_w(address)} }})', ["setfloating", f"address:{address}"])
    for prop, classic in (
        ("no_focus", "nofocus"),
        ("no_shadow", "noshadow"),
        ("no_blur", "noblur"),
        ("no_anim", "noanim"),
        ("border_size", "bordersize"),
        ("rounding", "rounding"),
    ):
        set_prop(address, prop, "0" if prop in ("border_size", "rounding") else "1", classic)


def _pin(address: str, enable: bool) -> None:
    pinned = any(c.get("address") == address and c.get("pinned") for c in clients())
    if pinned == enable:
        return
    # Klassisch schaltet "pin" nur um, deshalb vorher den Zustand prüfen
    _dispatch(
        f'hl.dsp.window.pin({{ action = "{"enable" if enable else "disable"}", {_w(address)} }})',
        ["pin", f"address:{address}"],
    )


PARK_WORKSPACE = "special:void-appraiser"


def _monitor_workspace(monitor: str) -> str | None:
    """Sichtbarer Arbeitsbereich eines Monitors, in Dispatcher-Schreibweise."""
    try:
        mons = json.loads(_hyprctl("monitors", "-j") or "[]")
    except ValueError:
        return None
    for m in mons:
        if m.get("name") == monitor:
            ws = m.get("activeWorkspace", {})
            # Benannte Arbeitsbereiche haben negative IDs
            return f"name:{ws['name']}" if ws.get("id", 0) < 0 else str(ws.get("id"))
    return None


def _move_silent(address: str, workspace: str) -> None:
    # follow = false: Der Fokus bleibt, wo er ist (sonst springt er mit)
    _dispatch(
        f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false, {_w(address)} }})',
        ["movetoworkspacesilent", f"{workspace},address:{address}"],
    )


def park(address: str) -> None:
    """Fenster auf einem versteckten Spezial-Arbeitsbereich ablegen, ohne den Fokus zu ändern."""
    _pin(address, False)
    _move_silent(address, PARK_WORKSPACE)


def place(address: str, monitor: str, x: int, y: int, w: int, h: int) -> None:
    """Fenster auf den sichtbaren Arbeitsbereich eines Monitors legen (Layout-Koordinaten).

    Anheften sorgt dafür, dass es auch bei Wechsel des Arbeitsbereichs sichtbar bleibt.
    """
    workspace = _monitor_workspace(monitor)
    if workspace:
        _move_silent(address, workspace)
    _dispatch(
        f"hl.dsp.window.resize({{ x = {w}, y = {h}, exact = true, {_w(address)} }})",
        ["resizewindowpixel", f"exact {w} {h},address:{address}"],
    )
    _dispatch(
        f"hl.dsp.window.move({{ x = {x}, y = {y}, exact = true, {_w(address)} }})",
        ["movewindowpixel", f"exact {x} {y},address:{address}"],
    )
    _pin(address, True)


def focus(address: str) -> None:
    _dispatch(f'hl.dsp.focus({{ {_w(address)} }})', ["focuswindow", f"address:{address}"])


def wait_for_window(title: str, timeout: float = 2.0) -> str | None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if address := find_window(title):
            return address
        time.sleep(0.05)
    return None
