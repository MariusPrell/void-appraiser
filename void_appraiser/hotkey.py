"""Global key for the manual scan.

Uses pynput. On Windows this works everywhere. On Linux/Wayland pynput only
sees keys sent to X11 windows; Warframe runs through Proton as an XWayland
window, so it works while the game is in the foreground.

The key is only read, never sent to the game.
"""

from __future__ import annotations

from typing import Callable

# Key name stored in the settings -> pynput name. Only keys rarely bound in the game.
KEYS = {
    "Off": None,
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
    "Insert": "insert",
    "Home": "home",
    "End": "end",
    "Page Up": "page_up",
    "Page Down": "page_down",
    "Pause": "pause",
    "Scroll Lock": "scroll_lock",
}

# Key names of version 0.8 and older (German) -> current names
LEGACY_KEYS = {
    "Aus": "Off",
    "Einfg": "Insert",
    "Pos1": "Home",
    "Ende": "End",
    "Bild auf": "Page Up",
    "Bild ab": "Page Down",
    "Rollen": "Scroll Lock",
}


def normalize(label: str) -> str:
    label = LEGACY_KEYS.get(label, label)
    return label if label in KEYS else "Insert"


class HotkeyListener:
    def __init__(self, key_label: str, callback: Callable[[], None]):
        self.key_label = normalize(key_label)
        self.callback = callback
        self._listener = None
        self.error: str | None = None

    def start(self) -> None:
        name = KEYS.get(self.key_label)
        if not name:
            return
        try:
            from pynput import keyboard

            target = getattr(keyboard.Key, name)
        except Exception as exc:  # e.g. no X server reachable
            self.error = str(exc)
            return

        def on_press(key):
            if key == target:
                self.callback()

        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
        except Exception as exc:
            self.error = str(exc)
            self._listener = None

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
