"""Scanner logic without a screen: header and cards are given."""

import numpy as np

from void_appraiser import scanner as sc
from void_appraiser.recognize import TextBox


class FakeRecognizer:
    def __init__(self):
        self.header = ""
        self.cards: list[str] = []

    def read_line(self, img):
        return TextBox(self.header, 0, 0, 1, 1)

    def read(self, img):
        # Cards side by side, as match_reward_cards expects them
        return [TextBox(name, 0.2 * i, 0.2, 0.2 * i + 0.15, 0.4) for i, name in enumerate(self.cards)]


class FakeBackend:
    def game_window(self):
        from void_appraiser.capture import GameWindow, Rect

        return GameWindow(Rect(0, 0, 1600, 900), True)

    def monitors(self):
        return []

    def grab(self, rect):
        return np.zeros((900, 1600, 3), dtype=np.uint8)


def make_scanner(monkeypatch):
    monkeypatch.setattr(sc.capture, "backend", lambda: FakeBackend())
    events = []
    names = ["Lex Prime Receiver", "Zylok Prime Barrel", "Kogake Prime Boot"]
    scanner = sc.Scanner(names, events.append, sc.ScannerSettings())
    scanner.recognizer = FakeRecognizer()
    return scanner, events


def kinds(events):
    return [type(e).__name__ for e in events if not isinstance(e, sc.ScannerStatus)]


def test_single_header_miss_does_not_close_rewards(monkeypatch):
    scanner, events = make_scanner(monkeypatch)
    rec = scanner.recognizer
    rec.header, rec.cards = "VOID FISSURE/REWARDS", ["Lex Prime Receiver", "Zylok Prime Barrel"]
    scanner._scan_once(False)
    rec.header = "VO1D F"  # header unreadable once
    scanner._scan_once(False)
    scanner._scan_once(False)
    rec.header = "VOID FISSURE/REWARDS"
    scanner._scan_once(False)
    assert kinds(events) == ["RewardsDetected"]


def test_rewards_close_after_three_misses(monkeypatch):
    scanner, events = make_scanner(monkeypatch)
    rec = scanner.recognizer
    rec.header, rec.cards = "VOID FISSURE/REWARDS", ["Lex Prime Receiver"]
    scanner._scan_once(False)
    rec.header = "ARSENAL"
    for _ in range(3):
        scanner._scan_once(False)
    assert kinds(events) == ["RewardsDetected", "RewardsGone"]


def test_fewer_cards_do_not_replace_full_list(monkeypatch):
    scanner, events = make_scanner(monkeypatch)
    rec = scanner.recognizer
    rec.header, rec.cards = "VOID FISSURE/REWARDS", ["Lex Prime Receiver", "Zylok Prime Barrel"]
    scanner._scan_once(False)
    rec.cards = ["Lex Prime Receiver"]  # OCR missed a card
    scanner._scan_once(False)
    rec.cards = ["Lex Prime Receiver", "Zylok Prime Barrel", "Kogake Prime Boot"]  # third card appears
    scanner._scan_once(False)
    detected = [e for e in events if isinstance(e, sc.RewardsDetected)]
    assert [len(e.cards) for e in detected] == [2, 3]


# --- Inventory and end-of-mission screen ------------------------------------

from void_appraiser.recognize import CATEGORY_LINE, HEADER_LINE, MISSION_LINE, crop  # noqa: E402

GRID_NAMES = ["Lex Prime Receiver", "Zylok Prime Barrel", "Kogake Prime Boot"]


class RegionRecognizer:
    """Answers read_line() depending on which region was cropped (regions differ in size)."""

    def __init__(self, frame_shape):
        frame = np.zeros(frame_shape, dtype=np.uint8)
        self.shapes = {
            crop(frame, HEADER_LINE).shape: "header",
            crop(frame, CATEGORY_LINE).shape: "category",
            crop(frame, MISSION_LINE).shape: "mission",
        }
        self.lines = {"header": "", "category": "", "mission": ""}
        self.items: list[str] = []
        self.reads = 0

    def read_line(self, img):
        text = self.lines.get(self.shapes.get(img.shape), "")
        return TextBox(text, 0, 0, 1, 1)

    def read(self, img):
        self.reads += 1
        return [TextBox(name, 0.1 + 0.2 * i, 0.5, 0.25 + 0.2 * i, 0.55) for i, name in enumerate(self.items)]


class FrameBackend(FakeBackend):
    def __init__(self):
        self.frame = np.zeros((900, 1600, 3), dtype=np.uint8)

    def grab(self, rect):
        return self.frame


def make_grid_scanner(monkeypatch):
    backend = FrameBackend()
    monkeypatch.setattr(sc.capture, "backend", lambda: backend)
    events = []
    scanner = sc.Scanner(GRID_NAMES, events.append, sc.ScannerSettings())
    scanner.recognizer = scanner.big_recognizer = RegionRecognizer(backend.frame.shape)
    scanner.inventory_matcher = scanner.matcher
    return scanner, backend, events


def test_inventory_is_read_again_after_scrolling(monkeypatch):
    scanner, backend, events = make_grid_scanner(monkeypatch)
    rec = scanner.recognizer
    rec.lines.update(header="INVENTORY/SELL", category="PRIME PARTS")
    rec.items = GRID_NAMES[:2]
    for _ in range(3):  # first view: read once it has settled, then not again
        scanner._scan_once(False)
    assert kinds(events) == ["InventoryVisible", "InventoryScanned"]

    backend.frame = np.full_like(backend.frame, 120)  # scrolled: the grid looks different
    scanner._scan_once(False)  # still moving
    scanner._scan_once(False)  # settled -> read again
    scanner._scan_once(False)
    assert kinds(events) == ["InventoryVisible", "InventoryScanned", "InventoryScanned"]


def test_mission_rewards_reported_once(monkeypatch):
    monkeypatch.setattr(sc.time, "monotonic", lambda clock=iter(range(0, 100000, 5)): next(clock))
    scanner, backend, events = make_grid_scanner(monkeypatch)
    rec = scanner.recognizer
    rec.lines.update(mission="MISSION COMPLETE")
    rec.items = GRID_NAMES[:2]
    for _ in range(3):
        scanner._scan_once(False)
    rec.lines.update(mission="")  # screen closes
    for _ in range(3):
        scanner._scan_once(False)
    rewards = [e for e in events if isinstance(e, sc.MissionRewards)]
    assert len(rewards) == 1
    assert sorted(i.name for i in rewards[0].items) == sorted(GRID_NAMES[:2])
