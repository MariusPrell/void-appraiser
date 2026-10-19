"""Controls our own windows on Hyprland (for the overlay).

Wayland programs may not place their windows themselves, so this goes through
`hyprctl dispatch`. Only our own overlay windows are touched, never any
Hyprland settings.

Hyprland 0.55+ with a Lua config expects Lua calls
(`hl.dsp.window.float({...})`), older versions the classic syntax.
Both are supported; the classic one is untested.
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
    """Floating, without border, shadow, animation and focus."""
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
    # The classic "pin" only toggles, so check the state first
    _dispatch(
        f'hl.dsp.window.pin({{ action = "{"enable" if enable else "disable"}", {_w(address)} }})',
        ["pin", f"address:{address}"],
    )


PARK_WORKSPACE = "special:void-appraiser"


def _monitor_workspace(monitor: str) -> str | None:
    """Visible workspace of a monitor, in dispatcher notation."""
    try:
        mons = json.loads(_hyprctl("monitors", "-j") or "[]")
    except ValueError:
        return None
    for m in mons:
        if m.get("name") == monitor:
            ws = m.get("activeWorkspace", {})
            # Named workspaces have negative IDs
            return f"name:{ws['name']}" if ws.get("id", 0) < 0 else str(ws.get("id"))
    return None


def _move_silent(address: str, workspace: str) -> None:
    # follow = false: the focus stays where it is (otherwise it moves along)
    _dispatch(
        f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false, {_w(address)} }})',
        ["movetoworkspacesilent", f"{workspace},address:{address}"],
    )


def park(address: str) -> None:
    """Park a window on a hidden special workspace without changing the focus."""
    _pin(address, False)
    _move_silent(address, PARK_WORKSPACE)


def place(address: str, monitor: str, x: int, y: int, w: int, h: int) -> None:
    """Put a window on the visible workspace of a monitor (layout coordinates).

    Pinning keeps it visible when the workspace changes.
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
