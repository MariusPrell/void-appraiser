"""Drop-Suche in den offiziellen Drop-Tabellen von Digital Extremes.

Quelle: https://www.warframe.com/droptables, aufbereitet als JSON von
drops.warframestat.us (Datei all.slim.json, rund 43.000 Einträge).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from .data import RELIC_DATA_MAX_AGE, _cached_json

DROPS_URL = "https://drops.warframestat.us/data/all.slim.json"
INFO_URL = "https://drops.warframestat.us/data/info.json"
MAX_RESULTS = 500

_TAGS = re.compile(r"<[^>]+>")
_REFINED = re.compile(r"Relic \((Exceptional|Flawless|Radiant)\)$")
_RELIC = re.compile(r"^(Lith|Meso|Neo|Axi|Requiem|Vanguard) (\w+) Relic(?: \((Exceptional|Flawless|Radiant)\))?$")


@dataclass(frozen=True)
class Drop:
    item: str
    place: str
    rarity: str
    chance: float | None  # in Prozent

    @property
    def relic(self) -> tuple[str, str, str] | None:
        """(Stufe, Name, Veredelung), wenn der Fundort ein Relikt ist."""
        m = _RELIC.match(self.place)
        return (m[1], m[2], m[3] or "Intact") if m else None


def _chance(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class DropTable:
    def __init__(self, raw: list[dict]):
        self.drops = [
            Drop(
                item=html.unescape(_TAGS.sub("", d.get("item", ""))).strip(),
                place=html.unescape(_TAGS.sub("", d.get("place", ""))).strip(),
                rarity=d.get("rarity") or "",
                chance=_chance(d.get("chance")),
            )
            for d in raw
            if d.get("item") and d.get("place")
        ]
        self._lower = [(d.item.lower(), d.place.lower()) for d in self.drops]

    @classmethod
    def load(cls) -> DropTable:
        return cls(_cached_json("drops_all.json", DROPS_URL, RELIC_DATA_MAX_AGE))

    def search(self, query: str, hide_refined: bool = True, in_places: bool = False) -> tuple[list[Drop], int]:
        """Alle Wörter der Suche müssen im Gegenstand vorkommen (oder, mit in_places,
        im Fundort). Gibt (Treffer, Gesamtzahl) zurück, sortiert nach Chance."""
        words = [w for w in query.lower().split() if w]
        if not words:
            return [], 0
        hits = []
        for drop, (item, place) in zip(self.drops, self._lower):
            text = place if in_places else item
            if all(w in text for w in words):
                if hide_refined and _REFINED.search(drop.place):
                    continue
                hits.append(drop)
        hits.sort(key=lambda d: (-(d.chance or 0), d.item, d.place))
        return hits[:MAX_RESULTS], len(hits)
