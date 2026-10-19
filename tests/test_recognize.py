from pathlib import Path

import numpy as np
import pytest

from warframe_helper.logwatch import RelicEquipped
from warframe_helper.recognize import (
    SCREEN_RELICS,
    SCREEN_REWARDS,
    NameMatcher,
    classify_header,
    TextBox,
    is_reward_header,
    match_reward_cards,
    parse_equip_dialog,
    ui_area,
)

NAMES = [
    "Lex Prime Receiver",
    "Nikana Prime Blueprint",
    "Nikana Prime Blade",
    "Ash Prime Neuroptics Blueprint",
    "2X Forma Blueprint",
    "Forma Blueprint",
]
SCREENSHOT = Path(__file__).parent.parent / "testdaten/screenshots/belohnung-121231.png"


def box(text, x0, y0, x1=None, y1=None):
    return TextBox(text, x0, y0, x1 if x1 is not None else x0 + 0.1, y1 if y1 is not None else y0 + 0.2)


def test_reward_header():
    assert is_reward_header([box("+ VOID FISSURE/REWARDS", 0, 0)])
    assert is_reward_header([box("+ VOLD FISSURE/REWARDS", 0, 0)])
    assert is_reward_header([box("+VOID FISSIRE/REWAROS", 0, 0)])
    assert is_reward_header([box("+ VOID FISSURE/REWARD", 0, 0)])
    assert is_reward_header([box("VOID", 0, 0), box("FISSURE/", 0, 0), box("R", 0, 0), box("W", 0, 0), box("RDS", 0, 0)])
    assert not is_reward_header([box("VOID FISSURES", 0, 0)])
    assert not is_reward_header([box("NAVIGATION", 0, 0)])


def test_relic_screen_header():
    assert classify_header([box("+ VOID RELICS/REEINEMENT", 0, 0)]) == SCREEN_RELICS
    assert classify_header([box("+ VOID RELICS /REFINEMENT", 0, 0)]) == SCREEN_RELICS
    assert classify_header([box("+VOID FISSURE/REWARDS", 0, 0)]) == SCREEN_REWARDS
    assert classify_header([box("SVOID FISSURELSELECT RELIC", 0, 0)]) == SCREEN_RELICS
    assert classify_header([box("ARSENAL", 0, 0)]) is None
    assert classify_header([box("", 0, 0)]) is None


def test_dialog():
    lines = [
        box("Are you sure you want to equip Axi Y3 Relic [RADIANT] for", 0.1, 0.40),
        box("this mission? It will be consumed if you seal the Void Fissure and extract.", 0.1, 0.45),
    ]
    assert parse_equip_dialog(lines) == RelicEquipped("Axi", "Y3", "Radiant")
    assert parse_equip_dialog([box("Are you sure you want to equip Lith P1 Relic for this mission?", 0, 0)]) == RelicEquipped("Lith", "P1", "Intact")
    # OCR-Fehler in der Veredelung und Zeilenumbruch im Namen
    assert parse_equip_dialog([box("want to equip Neo N8 Relic [FLAWLES5] for", 0, 0)]) == RelicEquipped("Neo", "N8", "Flawless")
    refine = "Are you sure you want to refine and equip Meso S8 Relic? It will cost 50 Void Traces"
    assert parse_equip_dialog([box(refine, 0, 0)]) == RelicEquipped("Meso", "S8", "Flawless")
    assert parse_equip_dialog([box("SKIP CINEMATIC?", 0, 0)]) is None


def test_matcher_tolerates_ocr_errors():
    m = NameMatcher(NAMES)
    assert m.match("Lex Prme Recelver")[0] == "Lex Prime Receiver"
    assert m.match("MariusPrell") is None
    assert m.match("2X Forma Blueprint")[0] == "2X Forma Blueprint"


def test_cards_with_wrapped_names_and_duplicates():
    m = NameMatcher(NAMES)
    boxes = [
        box("Ash Prime Neuroptics", 0.10, 0.20, 0.22, 0.40),
        box("Blueprint", 0.13, 0.42, 0.19, 0.62),
        box("Lex Prime Receiver", 0.35, 0.20, 0.47, 0.40),
        box("Lex Prime Receiver", 0.60, 0.20, 0.72, 0.40),
        box("Nikana Prime Blade", 0.85, 0.20, 0.97, 0.40),
        box("MariusPrell", 0.37, 0.70, 0.45, 0.90),
    ]
    cards = match_reward_cards(boxes, m)
    assert [c.name for c in cards] == [
        "Ash Prime Neuroptics Blueprint",
        "Lex Prime Receiver",
        "Lex Prime Receiver",
        "Nikana Prime Blade",
    ]


def test_ui_area():
    assert ui_area(2560, 1440) == (0, 0, 2560, 1440)
    assert ui_area(3440, 1440) == (440, 0, 2560, 1440)
    assert ui_area(1920, 1200) == (0, 60, 1920, 1080)


@pytest.mark.skipif(not SCREENSHOT.exists(), reason="Screenshot nicht vorhanden (nicht im Repo)")
def test_real_screenshot():
    from PIL import Image

    from warframe_helper.recognize import CARDS_REGION, HEADER_LINE, Recognizer, crop

    frame = np.asarray(Image.open(SCREENSHOT).convert("RGB"))[:, 1920:]  # nur der Spiel-Monitor
    rec = Recognizer()
    assert is_reward_header([rec.read_line(crop(frame, HEADER_LINE))])
    cards = match_reward_cards(rec.read(crop(frame, CARDS_REGION)), NameMatcher(NAMES))
    assert [c.name for c in cards] == ["Lex Prime Receiver"]


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def recognizer():
    from warframe_helper.recognize import Recognizer

    return Recognizer()


def _frame(name):
    from PIL import Image

    return np.asarray(Image.open(FIXTURES / name).convert("RGB"))


def test_fixture_three_cards(recognizer):
    from warframe_helper.recognize import CARDS_REGION, HEADER_LINE, crop

    frame = _frame("belohnung-3-karten.png")
    assert classify_header([recognizer.read_line(crop(frame, HEADER_LINE))]) == SCREEN_REWARDS
    names = ["Zylok Prime Barrel", "Caliban Prime Chassis Blueprint", "Kogake Prime Boot", "Caliban Prime Blueprint"]
    cards = match_reward_cards(recognizer.read(crop(frame, CARDS_REGION)), NameMatcher(names))
    assert [c.name for c in cards] == names[:3]


@pytest.mark.parametrize(
    "name, expected",
    [
        ("dialog-axi-z2-radiant.png", RelicEquipped("Axi", "Z2", "Radiant")),
        ("dialog-axi-a17-intact.png", RelicEquipped("Axi", "A17", "Intact")),
        # Relikt-Auswahl während einer Survival ("VOID FISSURE/SELECT RELIC"), Bild in 2000×1125
        ("dialog-survival-meso-e5.png", RelicEquipped("Meso", "E5", "Intact")),
    ],
)
def test_fixture_dialog(recognizer, name, expected):
    from warframe_helper.recognize import DIALOG_REGION, HEADER_LINE, crop

    frame = _frame(name)
    assert classify_header([recognizer.read_line(crop(frame, HEADER_LINE))]) == SCREEN_RELICS
    assert parse_equip_dialog(recognizer.read(crop(frame, DIALOG_REGION))) == expected
