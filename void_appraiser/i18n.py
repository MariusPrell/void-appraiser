"""User interface translations.

Source strings in the code are English. tr() returns the German translation
when German is selected. Placeholders use str.format syntax, e.g.
tr("{count} parts", count=3).
"""

from __future__ import annotations

LANGUAGES = {"en": "English", "de": "Deutsch"}

_language = "en"


def set_language(code: str) -> None:
    global _language
    _language = code if code in LANGUAGES else "en"


def language() -> str:
    return _language


def tr(text: str, **values) -> str:
    if _language == "de":
        text = DE.get(text, text)
    return text.format(**values) if values else text


def num(value: float | None, digits: int = 0) -> str:
    """Number with the separators of the selected language; "–" if unknown."""
    if value is None:
        return "–"
    text = f"{value:,.{digits}f}"
    if _language == "de":
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return text


# German translations live in i18n_de.py; keys are the English source strings
from .i18n_de import DE  # noqa: E402
