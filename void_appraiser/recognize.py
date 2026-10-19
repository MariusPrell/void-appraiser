"""Recognizes the reward screen, equip dialog and inventory on a screenshot.

All regions are given relative to a 16:9 area at screen height, so they fit
any resolution; see the anchor note below for wider screens.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

import numpy as np

from .logwatch import RelicEquipped

# Regions: (x0, y0, x1, y1, scale, anchor)
# Warframe scales its interface with the screen height. On wider screens
# (21:9, 32:9) it does not stay a centered 16:9 block but sticks to the
# edges: the header on the left, dialog and cards in the center. So the
# x values are fractions of an imaginary 16:9 area at screen height that sits at the anchor.
LEFT, CENTER, RIGHT = "left", "center", "right"
# Header line top left, e.g. "VOID FISSURE/REWARDS" or "VOID RELICS/REFINEMENT".
# Line recognition only, without text detection, very cheap. Wide, because squad
# icons in front of it push the text to the right.
HEADER_LINE = (0.04, 0.015, 0.52, 0.09, 0.5, LEFT)
CARDS_REGION = (0.08, 0.36, 0.92, 0.465, 1.0, CENTER)
# Text of the equip dialog in the screen center
DIALOG_REGION = (0.34, 0.40, 0.66, 0.52, 0.8, CENTER)

SCREEN_REWARDS = "rewards"
SCREEN_RELICS = "relics"
SCREEN_INVENTORY = "inventory"
# Relic selection exists in the orbiter (REFINEMENT) and during endless missions (SELECT RELIC).
# Each header consists of parts that must all appear (fuzzily).
# That way e.g. "VOID FISSURES" (navigation) does not count as the reward screen.
_HEADERS = [
    (SCREEN_REWARDS, ("VOIDFISSURE", "REWARDS")),
    (SCREEN_RELICS, ("VOIDRELICS", "REFINEMENT")),
    (SCREEN_RELICS, ("VOIDFISSURE", "SELECTRELIC")),
    (SCREEN_INVENTORY, ("INVENTORY",)),
]

# Below the inventory header is the category, e.g. "PRIME PARTS"
CATEGORY_LINE = (0.035, 0.092, 0.17, 0.14, 1.0, LEFT)
# Real headers score at least ~0.82 despite OCR errors, other screens at most ~0.45
HEADER_CUTOFF = 0.7

MATCH_CUTOFF = 0.8


@dataclass(frozen=True)
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float = 1.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class RewardCard:
    name: str
    x: float  # center of the card, relative (0 to 1) within the cropped region
    confidence: float


class Recognizer:
    """Text recognition (own engine in ocr.py). The model is loaded on first use."""

    def __init__(self, threads: int = 1):
        self.threads = threads
        self._engine = None

    def _get(self):
        if self._engine is None:
            from .ocr import OcrEngine

            self._engine = OcrEngine(threads=self.threads)
        return self._engine

    def read_line(self, img: np.ndarray) -> TextBox:
        """Reads a single line of text without text detection (fast)."""
        text, score = self._get().read_line(img)
        return TextBox(text.strip(), 0.0, 0.0, 1.0, 1.0, score)

    def read(self, img: np.ndarray) -> list[TextBox]:
        h, w = img.shape[:2]
        return [
            TextBox(line.text.strip(), line.box[0] / w, line.box[1] / h, line.box[2] / w, line.box[3] / h, line.score)
            for line in self._get().read(img)
        ]


def ui_area(width: int, height: int) -> tuple[int, int, int, int]:
    """Centered 16:9 area (x, y, w, h) at image height. For narrower images (16:10)
    at image width and vertically centered."""
    if width / height > 16 / 9 + 0.01:
        w = round(height * 16 / 9)
        return ((width - w) // 2, 0, w, height)
    if width / height < 16 / 9 - 0.01:
        h = round(width * 9 / 16)
        return (0, (height - h) // 2, width, h)
    return (0, 0, width, height)


def region_rect(width: int, height: int, region: tuple) -> tuple[int, int, int, int]:
    """Region (x, y, w, h) in pixels for an image of size width × height."""
    x0, y0, x1, y1 = region[:4]
    anchor = region[5] if len(region) > 5 else CENTER
    ax, ay, aw, ah = ui_area(width, height)
    if anchor == LEFT:
        ax = 0
    elif anchor == RIGHT:
        ax = width - aw
    x, y = ax + int(x0 * aw), ay + int(y0 * ah)
    return x, y, ax + int(x1 * aw) - x, ay + int(y1 * ah) - y


def crop(img: np.ndarray, region: tuple) -> np.ndarray:
    scale = region[4]
    x, y, w, h = region_rect(img.shape[1], img.shape[0], region)
    part = img[y : y + h, x : x + w]
    if scale != 1.0:
        from PIL import Image

        size = (max(1, int(part.shape[1] * scale)), max(1, int(part.shape[0] * scale)))
        part = np.asarray(Image.fromarray(part).resize(size, Image.BILINEAR))
    return np.ascontiguousarray(part)


# --- Evaluating the recognized text (testable without OCR) ---------------


def _plain(text: str) -> str:
    """Remove accents the OCR sometimes reads (e.g. "FLAWLÉSS")."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _squash(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _plain(text).upper())


def _best_window_ratio(text: str, target: str) -> float:
    """How well target appears anywhere in text (0 to 1), tolerant of OCR errors."""
    if not text:
        return 0.0
    n = len(target)
    windows = [text[i : i + n] for i in range(max(1, len(text) - n + 1))]
    return max(difflib.SequenceMatcher(None, w, target).ratio() for w in windows)


def classify_header(boxes: list[TextBox]) -> str | None:
    """Which screen is open? SCREEN_REWARDS, SCREEN_RELICS, SCREEN_INVENTORY or None."""
    text = _squash(" ".join(b.text for b in boxes))
    score, kind = max((min(_best_window_ratio(text, part) for part in parts), kind) for kind, parts in _HEADERS)
    return kind if score >= HEADER_CUTOFF else None


def is_reward_header(boxes: list[TextBox]) -> bool:
    return classify_header(boxes) == SCREEN_REWARDS


_DIALOG = re.compile(
    r"equip\s*(Lith|Meso|Neo|Axi|Requiem|Vanguard)\s*([A-Z]\s*\d+)\s*Relic\s*(?:\[\s*([A-Z0-9]+)\s*\])?",
    re.IGNORECASE,
)
_REFINE_COST = re.compile(r"refine\s*and\s*equip.*?cost\s*(\d+)", re.IGNORECASE)
_REFINEMENTS = ("Exceptional", "Flawless", "Radiant")
_COST_TO_REFINEMENT = {25: "Exceptional", 50: "Flawless", 100: "Radiant"}


def parse_equip_dialog(boxes: list[TextBox]) -> RelicEquipped | None:
    # Join lines in reading order, the dialog text can wrap
    lines = sorted(boxes, key=lambda b: (round(b.y0, 2), b.x0))
    text = _plain(" ".join(b.text for b in lines))
    m = _DIALOG.search(text)
    if not m:
        return None
    tier = m[1].capitalize()
    name = m[2].replace(" ", "").upper()
    refinement = "Intact"
    if m[3]:
        found = difflib.get_close_matches(m[3].capitalize(), _REFINEMENTS, n=1, cutoff=0.6)
        refinement = found[0] if found else "Intact"
    elif cost := _REFINE_COST.search(text):
        refinement = _COST_TO_REFINEMENT.get(int(cost[1]), "Intact")
    return RelicEquipped(tier, name, refinement)


class NameMatcher:
    """Maps recognized text to known part names (the OCR makes mistakes)."""

    def __init__(self, names: list[str]):
        self._by_key = {_squash(n): n for n in names}
        self._keys = list(self._by_key)

    def match(self, text: str) -> tuple[str, float] | None:
        key = _squash(text)
        if len(key) < 4:
            return None
        if key in self._by_key:
            return self._by_key[key], 1.0
        found = difflib.get_close_matches(key, self._keys, n=1, cutoff=MATCH_CUTOFF)
        if not found:
            return None
        # A fragment (e.g. only the second line "Chassis Blueprint") must not match
        # a much longer name
        if len(key) < 0.8 * len(found[0]):
            return None
        # The name before "PRIME" (Warframe or weapon) must match as well, otherwise an
        # unreadable beginning lets the length decide (e.g. "..IME CHASSIS BLUEPRINT" -> Nyx)
        base = found[0].split("PRIME")[0] if "PRIME" in found[0] else ""
        if base and _best_window_ratio(key[: len(base) + 2], base) < 0.6:
            return None
        ratio = difflib.SequenceMatcher(None, key, found[0]).ratio()
        return self._by_key[found[0]], ratio


def _line_below(box: TextBox, other: TextBox) -> bool:
    """Is other the next line of the same name (directly below, overlapping horizontally)?
    Detected boxes are slightly enlarged and therefore often overlap a little."""
    height = box.y1 - box.y0
    return (
        other.y0 > box.y0 + 0.3 * height
        and other.y0 - box.y1 < 1.2 * height
        and other.x0 < box.x1
        and other.x1 > box.x0
    )


def _name_options(boxes: list[TextBox], i: int) -> list[tuple[str, TextBox]]:
    """Possible names starting at line i: the line alone, with the next one and with two more."""
    box = boxes[i]
    options = [(box.text, box)]
    for second in boxes[i + 1 :]:
        if _line_below(box, second):
            options.append((f"{box.text} {second.text}", second))
            for third in boxes[i + 1 :]:
                if third is not second and _line_below(second, third):
                    options.append((f"{box.text} {second.text} {third.text}", third))
    return options


def match_reward_cards(boxes: list[TextBox], matcher: NameMatcher) -> list[RewardCard]:
    """Finds the part names on the cards, even when they span two lines."""
    boxes = sorted(boxes, key=lambda b: (b.y0, b.x0))
    candidates: list[RewardCard] = []
    for i, box in enumerate(boxes):
        options = [(text, (box.cx + last.cx) / 2) for text, last in _name_options(boxes, i)]
        for text, cx in options:
            if found := matcher.match(text):
                candidates.append(RewardCard(found[0], cx, found[1]))
    # Keep only the best match per card (position)
    candidates.sort(key=lambda c: -c.confidence)
    cards: list[RewardCard] = []
    for cand in candidates:
        if all(abs(cand.x - c.x) > 0.06 for c in cards):
            cards.append(cand)
    return sorted(cards, key=lambda c: c.x)


# --- Inventory (prime parts) ----------------------------------------------


def is_prime_parts(box: TextBox) -> bool:
    return _best_window_ratio(_squash(box.text), "PRIMEPARTS") >= 0.75


def inventory_grid_rect(width: int, height: int) -> tuple[int, int, int, int]:
    """Region with the part tiles. The grid starts on the left and reaches the sell
    column on the right edge; wide screens have more columns."""
    ax, ay, aw, ah = ui_area(width, height)
    x0 = int(0.03 * ah)
    x1 = width - int(0.56 * ah)
    return x0, ay + int(0.165 * ah), max(1, x1 - x0), int(0.82 * ah)


@dataclass(frozen=True)
class GridItem:
    name: str
    count: int
    x: float  # center of the name in pixels
    y: float  # top of the name in pixels
    confidence: float


_BADGE = re.compile(r"^\W{0,2}\s*(\d{1,3})$")


def match_grid_items(boxes: list[TextBox], matcher: NameMatcher, unit: float) -> list[GridItem]:
    """Recognize parts in the inventory grid, including the count from the small badges ("✓2").

    boxes in pixels, unit = height of the game interface (all distances scale with it).
    """
    badges = []
    texts = []
    for box in boxes:
        m = _BADGE.match(_plain(box.text).strip())
        if m:
            if int(m[1]) >= 2:  # single parts have no badge
                badges.append((box, int(m[1])))
        else:
            texts.append(box)

    texts.sort(key=lambda b: (b.y0, b.x0))
    candidates = []
    for i, box in enumerate(texts):
        for text, last in _name_options(texts, i):
            if found := matcher.match(text):
                cx = (min(box.x0, last.x0) + max(box.x1, last.x1)) / 2
                candidates.append((found[1], len(text), found[0], cx, box.y0))
    # Only the best match per tile (the longest one on a tie)
    candidates.sort(key=lambda c: (-c[0], -c[1]))
    items: list[list] = []
    for conf, _, name, cx, y in candidates:
        if all(abs(cx - it[1]) > 0.09 * unit or abs(y - it[2]) > 0.09 * unit for it in items):
            items.append([name, cx, y, conf, 1])

    # Badges sit at the top left of the tile, about 0.1 × height above the name
    for badge, count in badges:
        best = None
        for it in items:
            dy = it[2] - badge.y1
            dx = badge.cx - (it[1] - 0.06 * unit)
            if 0.02 * unit < dy < 0.17 * unit and abs(dx) < 0.07 * unit:
                score = abs(dx) + abs(dy - 0.09 * unit)
                if best is None or score < best[0]:
                    best = (score, it)
        if best:
            best[1][4] = count

    items.sort(key=lambda it: (round(it[2] / (0.05 * unit)), it[1]))
    return [GridItem(name, count, cx, y, conf) for name, cx, y, conf, count in items]


def read_inventory(frame: np.ndarray, recognizer: "Recognizer", matcher: NameMatcher) -> list[GridItem]:
    """Read the visible parts in the inventory (expensive, only on a key press).

    Second pass: if no text was recognized above a name fragment ("Receiver"), the
    line above is read directly. The first line often lies on the picture of the
    part and is easily missed by the text detection. The same goes for a missing
    second line below a first line.
    """
    height, width = frame.shape[:2]
    unit = ui_area(width, height)[3]
    gx, gy, gw, gh = inventory_grid_rect(width, height)
    grid = np.ascontiguousarray(frame[gy : gy + gh, gx : gx + gw])
    boxes = [
        TextBox(b.text, b.x0 * gw, b.y0 * gh, b.x1 * gw, b.y1 * gh, b.score) for b in recognizer.read(grid)
    ]

    def read_at(x_center: float, y0: float, y1: float) -> None:
        x0 = int(max(0, x_center - 0.09 * unit))
        x1 = int(min(gw, x_center + 0.09 * unit))
        y0, y1 = int(max(0, y0)), int(min(gh, y1))
        if x1 - x0 < 10 or y1 - y0 < 8:
            return
        line = recognizer.read_line(np.ascontiguousarray(grid[y0:y1, x0:x1]))
        if line.text:
            extra.append(TextBox(line.text, x0, y0, x1, y1, line.score))

    extra: list[TextBox] = []
    for box in boxes:
        if _BADGE.match(_plain(box.text).strip()):
            continue
        line_h = box.y1 - box.y0
        has_prime = _best_window_ratio(_squash(box.text), "PRIME") >= 0.8
        if not has_prime and not any(_line_below(other, box) for other in boxes):
            # Name fragment without first line: read above
            read_at(box.cx, box.y0 - 0.95 * line_h, box.y0 + 0.15 * line_h)
        elif has_prime and not any(_line_below(box, other) for other in boxes):
            # First line without second: read below in case the name may be incomplete
            exact = matcher.match(box.text)
            complete = exact and exact[1] == 1.0 and not matcher.match(exact[0] + " Blueprint")
            if not complete:
                read_at(box.cx, box.y1 - 0.15 * line_h, box.y1 + 0.95 * line_h)
    return match_grid_items(boxes + extra, matcher, unit)
