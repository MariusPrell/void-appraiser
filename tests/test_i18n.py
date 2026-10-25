"""Every translated UI string has a German translation with the same placeholders."""

import ast
import re
from pathlib import Path

from void_appraiser import hotkey, i18n
from void_appraiser.i18n_de import DE

PACKAGE = Path(__file__).parent.parent / "void_appraiser"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _tr_strings() -> set[str]:
    """All string literals passed to tr(...) in the package."""
    found = set()
    for path in PACKAGE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
    return found


def test_all_strings_translated():
    # Strings that are passed to tr() indirectly (column names, keys, cycle states, fissure kinds)
    indirect = {k for k in hotkey.KEYS if not k.startswith("F")} | {"Day", "Night", "Warm", "Cold", "Normal", "Steel Path", "Void Storm"}
    indirect |= {"Part", "Count", "Platinum", "Ducats", "Ducats per platinum", "Platinum total", "Ducats total"}
    indirect |= {"Item", "Location", "Rarity", "Chance"}
    missing = sorted((_tr_strings() | indirect) - set(DE))
    assert not missing, missing


def test_placeholders_match():
    for english, german in DE.items():
        assert set(PLACEHOLDER.findall(english)) == set(PLACEHOLDER.findall(german)), english


def test_switch_language_and_numbers():
    try:
        i18n.set_language("de")
        assert i18n.tr("{value} platinum", value=5) == "5 Platin"
        assert i18n.num(1234.5, 1) == "1.234,5"
        i18n.set_language("en")
        assert i18n.tr("{value} platinum", value=5) == "5 platinum"
        assert i18n.num(1234.5, 1) == "1,234.5"
        i18n.set_language("xx")  # unknown -> English
        assert i18n.language() == "en"
    finally:
        i18n.set_language("en")


def test_legacy_key_names():
    assert hotkey.normalize("Einfg") == "Insert"
    assert hotkey.normalize("Aus") == "Off"
    assert hotkey.normalize("F9") == "F9"
    assert hotkey.normalize("nonsense") == "Insert"


def test_easter_egg_trigger():
    from void_appraiser import easteregg

    assert easteregg.is_trigger("  Rebecca  Ford ")
    assert not easteregg.is_trigger("rebecca prime")
