"""Schaut regelmäßig (oder auf Tastendruck) auf den Bildschirm.

Ablauf pro Durchgang:
1. Nur weitermachen, wenn Warframe im Vordergrund ist (automatischer Modus).
2. Kopfzeile lesen (billig).
3. "VOID FISSURE/REWARDS": die Karten lesen.
4. "VOID RELICS/REFINEMENT" (Relikt-Auswahl): die Bildmitte nach dem Ausrüsten-Dialog absuchen.
   Beim manuellen Scan wird der Dialog immer gesucht.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import capture
from .logwatch import RelicEquipped
from .recognize import (
    CARDS_REGION,
    DIALOG_REGION,
    HEADER_LINE,
    SCREEN_RELICS,
    SCREEN_REWARDS,
    NameMatcher,
    Recognizer,
    RewardCard,
    classify_header,
    crop,
    match_reward_cards,
    parse_equip_dialog,
)


@dataclass(frozen=True)
class RewardsDetected:
    cards: tuple[RewardCard, ...]


@dataclass(frozen=True)
class RewardsGone:
    pass


@dataclass(frozen=True)
class DialogDetected:
    """Ausrüsten-Dialog auf dem Bildschirm (im Gegensatz zum verspäteten Log)."""

    relic: RelicEquipped


@dataclass(frozen=True)
class ScannerStatus:
    text: str


@dataclass
class ScannerSettings:
    auto: bool = True
    interval: float = 1.5
    monitor: str = ""  # leer = automatisch (Warframe-Fenster)
    debug_dir: Path | None = None


class Scanner:
    def __init__(self, names: list[str], on_event: Callable[[object], None], settings: ScannerSettings):
        self.matcher = NameMatcher(names)
        self.on_event = on_event
        self.settings = settings
        self.recognizer = Recognizer(threads=1)
        self._wake = threading.Event()
        self._manual = False
        self._stop = False
        self._rewards_visible = False
        self._last_cards: tuple[str, ...] = ()
        self._last_relic: tuple[RelicEquipped, float] | None = None
        self._last_status = ""
        self._thread = threading.Thread(target=self._run, name="Scanner", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def scan_now(self) -> None:
        """Einmal sofort scannen, auch wenn die Automatik aus ist."""
        self._manual = True
        self._wake.set()

    def settings_changed(self) -> None:
        self._wake.set()

    # ------------------------------------------------------------------

    def _status(self, text: str) -> None:
        if text != self._last_status:
            self._last_status = text
            self.on_event(ScannerStatus(text))

    def _run(self) -> None:
        while not self._stop:
            manual, self._manual = self._manual, False
            if manual or self.settings.auto:
                try:
                    self._scan_once(manual)
                except Exception as exc:  # Erkennung darf das Programm nie beenden
                    self._status(f"Erkennung: Fehler ({exc})")
            else:
                self._status("Erkennung: automatisch aus")
            # Bei offenem Belohnungsbildschirm öfter schauen, Karten kommen nacheinander
            wait = 0.75 if self._rewards_visible else self.settings.interval
            self._wake.wait(wait)
            self._wake.clear()

    def _target(self, manual: bool) -> capture.Rect | None:
        be = capture.backend()
        if self.settings.monitor:
            for mon in be.monitors():
                if mon.name == self.settings.monitor:
                    window = be.game_window()
                    if not manual and window is not None and not window.focused:
                        self._status("Erkennung: wartet (Warframe nicht im Vordergrund)")
                        return None
                    return mon.rect
            self._status(f"Erkennung: Monitor {self.settings.monitor} nicht gefunden")
            return None
        window = be.game_window()
        if window is None:
            mons = be.monitors()
            if not mons:
                self._status("Erkennung: kein Monitor gefunden")
                return None
            if not manual:
                self._status("Erkennung: Warframe-Fenster nicht gefunden")
                return None
            return mons[0].rect
        if not window.focused and not manual:
            self._status("Erkennung: wartet (Warframe nicht im Vordergrund)")
            return None
        return window.rect

    def _scan_once(self, manual: bool) -> None:
        rect = self._target(manual)
        if rect is None:
            if self._rewards_visible:
                self._set_rewards_gone()
            return
        self._status("Erkennung: aktiv")
        frame = capture.backend().grab(rect)
        started = time.monotonic()

        screen = classify_header([self.recognizer.read_line(crop(frame, HEADER_LINE))])
        if screen == SCREEN_REWARDS:
            cards = match_reward_cards(self.recognizer.read(crop(frame, CARDS_REGION)), self.matcher)
            self._rewards_visible = True
            names = tuple(c.name for c in cards)
            if names and names != self._last_cards:
                self._last_cards = names
                self.on_event(RewardsDetected(tuple(cards)))
                self._debug_save(frame, "belohnung", True)
            elif manual:
                self._debug_save(frame, "belohnung", True)
            return
        if self._rewards_visible:
            self._set_rewards_gone()
        if screen != SCREEN_RELICS and not manual:
            return

        relic = parse_equip_dialog(self.recognizer.read(crop(frame, DIALOG_REGION)))
        if relic:
            # Derselbe Dialog bleibt mehrere Durchgänge offen: nur einmal melden
            if not self._last_relic or self._last_relic[0] != relic or time.monotonic() - self._last_relic[1] > 30:
                self.on_event(DialogDetected(relic))
                self._debug_save(frame, "dialog", True)
            self._last_relic = (relic, time.monotonic())
        elif manual:
            self._debug_save(frame, "manuell", True)
        if manual:
            self._status(f"Erkennung: manueller Scan fertig ({(time.monotonic() - started) * 1000:.0f} ms)")

    def _set_rewards_gone(self) -> None:
        self._rewards_visible = False
        self._last_cards = ()
        self.on_event(RewardsGone())

    def _debug_save(self, frame, kind: str, condition: bool) -> None:
        if not (self.settings.debug_dir and condition):
            return
        from PIL import Image

        self.settings.debug_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.debug_dir / f"{kind}-{time.strftime('%Y%m%d-%H%M%S')}.png"
        if not path.exists():
            Image.fromarray(frame).save(path)
