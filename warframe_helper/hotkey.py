"""Globale Taste für den manuellen Scan.

Nutzt pynput. Unter Windows geht das überall. Unter Linux/Wayland sieht pynput
nur Tasten, die an X11-Fenster gehen; Warframe läuft über Proton als
XWayland-Fenster, also klappt es, solange das Spiel im Vordergrund ist.

Die Taste wird nur gelesen, nie an das Spiel gesendet.
"""

from __future__ import annotations

from typing import Callable

# Angezeigter Name -> pynput-Name. Nur Tasten, die im Spiel selten belegt sind.
KEYS = {
    "Aus": None,
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
    "Einfg": "insert",
    "Pos1": "home",
    "Ende": "end",
    "Bild auf": "page_up",
    "Bild ab": "page_down",
    "Pause": "pause",
    "Rollen": "scroll_lock",
}


class HotkeyListener:
    def __init__(self, key_label: str, callback: Callable[[], None]):
        self.key_label = key_label
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
        except Exception as exc:  # z. B. kein X-Server erreichbar
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
