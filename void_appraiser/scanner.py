"""Looks at the screen regularly (or on a key press).

Each pass:
1. Only continue while Warframe is in the foreground (automatic mode).
2. Read the header line (cheap).
3. "VOID FISSURE/REWARDS": read the cards.
4. "VOID RELICS/REFINEMENT" (relic selection): search the screen center for the equip dialog.
   A manual scan always looks for the dialog.
5. "INVENTORY" with category "PRIME PARTS": read the grid automatically when it has
   changed (e.g. after scrolling) and settled, or on a key press.
6. "MISSION COMPLETE" (end-of-mission screen): read the received prime parts and
   report them once when the screen closes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import capture
from .i18n import tr
from .logwatch import RelicEquipped
from .recognize import (
    CARDS_REGION,
    DIALOG_REGION,
    HEADER_LINE,
    CATEGORY_LINE,
    MISSION_LINE,
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
    inventory_grid_rect,
    is_mission_complete,
    is_prime_parts,
    mission_grid_rect,
    parse_equip_dialog,
    read_inventory,
    read_mission_rewards,
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
class MissionRewards:
    """Prime parts received in a mission (read from the end-of-mission screen)."""

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
        self._grid_last: np.ndarray | None = None  # grid thumbnail of the previous pass
        self._grid_scanned: np.ndarray | None = None  # grid thumbnail of the last read
        self._mission_visible = False
        self._mission_misses = 0
        self._mission_items: dict[str, GridItem] = {}
        self._mission_last_read = 0.0
        # Already reported counts of the current mission, in case the screen comes back
        # (e.g. after alt-tab) - then only the difference is reported
        self._mission_reported: dict[str, int] = {}
        self._mission_reported_at = 0.0
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
            # Look more often while the reward screen is open (cards appear one after another)
            # or the inventory is open (react quickly to scrolling)
            busy = self._rewards_visible or self._inventory_visible
            wait = 0.75 if busy else self.settings.interval
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
            self._mission_missed()
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
                if manual or self._grid_changed(frame):
                    self._scan_inventory(frame, started)
                return
        self._inventory_missed()

        if screen is None and is_mission_complete(self.recognizer.read_line(crop(frame, MISSION_LINE))):
            self._mission_seen(frame)
            return
        self._mission_missed()
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
            if not visible:
                self._grid_last = self._grid_scanned = None
            self.on_event(InventoryVisible(visible))

    # --- End-of-mission screen ----------------------------------------------

    def _mission_seen(self, frame) -> None:
        """Collect the received parts while the screen is open; the grid can be scrolled,
        so it is read again every few seconds. Highest count per part wins."""
        self._mission_misses = 0
        if not self._mission_visible:
            self._mission_visible = True
            self._mission_last_read = 0.0
            if time.monotonic() - self._mission_reported_at > 60:
                self._mission_items = {}
                self._mission_reported = {}
                self._debug_save(frame, "mission", True)
        if self.inventory_matcher is None or time.monotonic() - self._mission_last_read < 3.0:
            return
        self._mission_last_read = time.monotonic()
        for item in read_mission_rewards(frame, self.big_recognizer, self.inventory_matcher):
            known = self._mission_items.get(item.name)
            if known is None or item.count > known.count:
                self._mission_items[item.name] = item

    def _mission_missed(self) -> None:
        if not self._mission_visible:
            return
        self._mission_misses += 1
        if self._mission_misses >= REWARDS_GONE_AFTER:
            self._mission_visible = False
            new = []
            for item in self._mission_items.values():
                extra = item.count - self._mission_reported.get(item.name, 0)
                if extra > 0:
                    new.append(GridItem(item.name, extra, item.x, item.y, item.confidence))
                    self._mission_reported[item.name] = item.count
            self._mission_reported_at = time.monotonic()
            if new:
                self.on_event(MissionRewards(tuple(new)))

    def _inventory_missed(self) -> None:
        # As with the reward screen: only hide after several misses in a row
        if self._inventory_visible:
            self._inventory_misses += 1
            if self._inventory_misses >= REWARDS_GONE_AFTER:
                self._set_inventory_visible(False)

    def _grid_changed(self, frame) -> bool:
        """Has the inventory grid changed since the last read and settled again?

        Compares small grayscale thumbnails: "settled" = almost no change since the
        previous pass (scrolling has stopped), "changed" = clearly different from the
        thumbnail of the last read. The first view of the inventory counts as changed.
        """
        x, y, w, h = inventory_grid_rect(frame.shape[1], frame.shape[0])
        thumb = _thumbnail(frame[y : y + h, x : x + w])
        settled = self._grid_last is not None and _difference(thumb, self._grid_last) < 3.0
        self._grid_last = thumb
        if not settled:
            return False
        if self._grid_scanned is not None and _difference(thumb, self._grid_scanned) < 6.0:
            return False
        return True

    def _scan_inventory(self, frame, started: float) -> None:
        if self.inventory_matcher is None:
            self._status(tr("Detection: market data still missing, scan the inventory again later"))
            return
        self._status(tr("Detection: reading inventory …"))
        items = read_inventory(frame, self.big_recognizer, self.inventory_matcher)
        x, y, w, h = inventory_grid_rect(frame.shape[1], frame.shape[0])
        self._grid_scanned = _thumbnail(frame[y : y + h, x : x + w])
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


def _thumbnail(img: np.ndarray) -> np.ndarray:
    """Small grayscale image (64 × 24) for cheap change detection."""
    from PIL import Image

    return np.asarray(Image.fromarray(img).convert("L").resize((64, 24), Image.BILINEAR), dtype=np.float32)


def _difference(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())
