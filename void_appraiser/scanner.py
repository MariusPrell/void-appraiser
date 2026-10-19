"""Looks at the screen regularly (or on a key press).

Each pass:
1. Only continue while Warframe is in the foreground (automatic mode).
2. Read the header line (cheap).
3. "VOID FISSURE/REWARDS": read the cards.
4. "VOID RELICS/REFINEMENT" (relic selection): search the screen center for the equip dialog.
   A manual scan always looks for the dialog.
5. "INVENTORY" with category "PRIME PARTS": show a hint. The grid is only read on a
   manual scan (key), because that is expensive.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import capture
from .i18n import tr
from .logwatch import RelicEquipped
from .recognize import (
    CARDS_REGION,
    DIALOG_REGION,
    HEADER_LINE,
    CATEGORY_LINE,
    SCREEN_INVENTORY,
    SCREEN_RELICS,
    SCREEN_REWARDS,
    GridItem,
    NameMatcher,
    Recognizer,
    RewardCard,
    classify_header,
    crop,
    match_reward_cards,
    is_prime_parts,
    parse_equip_dialog,
    read_inventory,
)


# Number of consecutive scans without the header until the reward screen counts as closed
# (while it is open we scan every 0.75 s, so about 2 s)
REWARDS_GONE_AFTER = 3


@dataclass(frozen=True)
class RewardsDetected:
    cards: tuple[RewardCard, ...]


@dataclass(frozen=True)
class RewardsGone:
    pass


@dataclass(frozen=True)
class DialogDetected:
    """Equip dialog on screen (as opposed to the delayed log)."""

    relic: RelicEquipped


@dataclass(frozen=True)
class InventoryVisible:
    """Inventory with "PRIME PARTS" is open (True) or closed again (False)."""

    visible: bool


@dataclass(frozen=True)
class InventoryScanned:
    items: tuple[GridItem, ...]


@dataclass(frozen=True)
class ScannerStatus:
    text: str


@dataclass
class ScannerSettings:
    auto: bool = True
    interval: float = 1.5
    monitor: str = ""  # empty = automatic (Warframe window)
    debug_dir: Path | None = None


class Scanner:
    def __init__(self, names: list[str], on_event: Callable[[object], None], settings: ScannerSettings):
        self.matcher = NameMatcher(names)
        self.on_event = on_event
        self.settings = settings
        self.recognizer = Recognizer(threads=1)
        # More threads for the large inventory grid, it only runs on a key press
        self.big_recognizer = Recognizer(threads=4)
        self.inventory_matcher: NameMatcher | None = None  # set from outside once market data is loaded
        self._inventory_visible = False
        self._inventory_misses = 0
        self._wake = threading.Event()
        self._manual = False
        self._stop = False
        self._rewards_visible = False
        self._rewards_misses = 0
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
        """Scan once right away, even if automatic detection is off."""
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
                except Exception as exc:  # detection must never end the program
                    self._status(tr("Detection: error ({error})", error=exc))
            else:
                self._status(tr("Detection: automatic off"))
            # Look more often while the reward screen is open, cards appear one after another
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
                        self._status(tr("Detection: waiting (Warframe not in the foreground)"))
                        return None
                    return mon.rect
            self._status(tr("Detection: monitor {name} not found", name=self.settings.monitor))
            return None
        window = be.game_window()
        if window is None:
            mons = be.monitors()
            if not mons:
                self._status(tr("Detection: no monitor found"))
                return None
            if not manual:
                self._status(tr("Detection: Warframe window not found"))
                return None
            return mons[0].rect
        if not window.focused and not manual:
            self._status(tr("Detection: waiting (Warframe not in the foreground)"))
            return None
        return window.rect

    def _scan_once(self, manual: bool) -> None:
        rect = self._target(manual)
        if rect is None:
            self._rewards_missed()
            self._inventory_missed()
            return
        self._status(tr("Detection: active"))
        frame = capture.backend().grab(rect)
        started = time.monotonic()

        screen = classify_header([self.recognizer.read_line(crop(frame, HEADER_LINE))])
        if screen == SCREEN_REWARDS:
            cards = match_reward_cards(self.recognizer.read(crop(frame, CARDS_REGION)), self.matcher)
            self._rewards_visible = True
            self._rewards_misses = 0
            names = tuple(c.name for c in cards)
            # A scan with fewer cards (OCR missed one) does not replace a complete list.
            # In a squad, new cards appear one after another, so more cards are allowed.
            if names and names != self._last_cards and len(names) >= len(self._last_cards):
                self._last_cards = names
                self.on_event(RewardsDetected(tuple(cards)))
                self._debug_save(frame, "rewards", True)
            elif manual:
                self._debug_save(frame, "rewards", True)
            return
        if self._rewards_missed():
            return  # reward screen probably still open, only the header was not read

        if screen == SCREEN_INVENTORY:
            category = self.recognizer.read_line(crop(frame, CATEGORY_LINE))
            if is_prime_parts(category):
                self._set_inventory_visible(True)
                if manual:
                    self._scan_inventory(frame, started)
                return
        self._inventory_missed()
        if screen != SCREEN_RELICS and not manual:
            return

        relic = parse_equip_dialog(self.recognizer.read(crop(frame, DIALOG_REGION)))
        if relic:
            # The same dialog stays open for several passes: report it only once
            if not self._last_relic or self._last_relic[0] != relic or time.monotonic() - self._last_relic[1] > 30:
                self.on_event(DialogDetected(relic))
                self._debug_save(frame, "dialog", True)
            self._last_relic = (relic, time.monotonic())
        elif manual:
            self._debug_save(frame, "manual", True)
        if manual:
            self._status(tr("Detection: manual scan done ({ms} ms)", ms=f"{(time.monotonic() - started) * 1000:.0f}"))

    # --- Inventory ----------------------------------------------------------

    def _set_inventory_visible(self, visible: bool) -> None:
        self._inventory_misses = 0
        if visible != self._inventory_visible:
            self._inventory_visible = visible
            self.on_event(InventoryVisible(visible))

    def _inventory_missed(self) -> None:
        # As with the reward screen: only hide after several misses in a row
        if self._inventory_visible:
            self._inventory_misses += 1
            if self._inventory_misses >= REWARDS_GONE_AFTER:
                self._set_inventory_visible(False)

    def _scan_inventory(self, frame, started: float) -> None:
        if self.inventory_matcher is None:
            self._status(tr("Detection: market data still missing, scan the inventory again later"))
            return
        self._status(tr("Detection: reading inventory …"))
        items = read_inventory(frame, self.big_recognizer, self.inventory_matcher)
        self.on_event(InventoryScanned(tuple(items)))
        self._debug_save(frame, "inventory", True)
        self._status(
            tr(
                "Detection: {count} parts read ({ms} ms)",
                count=len(items),
                ms=f"{(time.monotonic() - started) * 1000:.0f}",
            )
        )

    def _rewards_missed(self) -> bool:
        """Header not recognized. Only after several misses in a row does the reward
        screen count as closed, otherwise the overlay flickers.

        Returns True while the screen still counts as open.
        """
        if not self._rewards_visible:
            return False
        self._rewards_misses += 1
        if self._rewards_misses >= REWARDS_GONE_AFTER:
            self._set_rewards_gone()
            return False
        return True

    def _set_rewards_gone(self) -> None:
        self._rewards_visible = False
        self._rewards_misses = 0
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
