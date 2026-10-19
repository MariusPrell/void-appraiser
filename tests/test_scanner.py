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
