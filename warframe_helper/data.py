"""Relikt-Inhalte (drops.warframestat.us) und Preise (warframe.market) mit Cache."""

from __future__ import annotations

import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .paths import cache_dir

RELICS_URL = "https://drops.warframestat.us/data/relics.json"
MARKET_API = "https://api.warframe.market/v2"
USER_AGENT = f"warframe-helper/{__version__}"

RELIC_DATA_MAX_AGE = 24 * 3600
ITEM_LIST_MAX_AGE = 24 * 3600
PRICE_MAX_AGE = 3600
# warframe.market erlaubt etwa 3 Anfragen pro Sekunde, wir bleiben deutlich darunter
MARKET_MIN_INTERVAL = 0.5
MARKET_RETRIES = 3  # bei Fehlern (z. B. 429 "zu viele Anfragen") mit wachsender Pause

TIERS = ("Lith", "Meso", "Neo", "Axi", "Requiem")
REFINEMENTS = ("Intact", "Exceptional", "Flawless", "Radiant")


@dataclass(frozen=True)
class Reward:
    name: str
    rarity: str
    chance: float  # in Prozent


@dataclass(frozen=True)
class Price:
    median: float | None  # Median der günstigsten Verkaufsangebote
    lowest: int | None
    offers: int
    fetched: float

    @property
    def value(self) -> float | None:
        return self.median


def _http_json(url: str, timeout: float = 20) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Language": "en"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cached_json(name: str, url: str, max_age: float) -> dict:
    """Lädt eine Datei, wenn der Cache älter als max_age ist. Bei Netzfehlern gilt der alte Cache."""
    path = cache_dir() / name
    if path.is_file() and time.time() - path.stat().st_mtime < max_age:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        data = _http_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        raise
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
    return data


def rarity_for(intact_chance: float | None, fallback: str) -> str:
    """Intact-Chancen: Common 25,33 %, Uncommon 11 %, Rare 2 %."""
    if intact_chance is None:
        return fallback
    if intact_chance >= 20:
        return "Common"
    if intact_chance >= 5:
        return "Uncommon"
    return "Rare"


class RelicDB:
    """Inhalt aller Relikte, Schlüssel: ("Axi", "C12", "Radiant")."""

    def __init__(self, raw: dict):
        self._relics: dict[tuple[str, str, str], list[Reward]] = {}
        for relic in raw.get("relics", []):
            if not all(k in relic for k in ("tier", "relicName", "state", "rewards")):
                continue  # Die Quelle enthält vereinzelt kaputte Einträge
            key = (relic["tier"], relic["relicName"], relic["state"])
            rewards = [Reward(r["itemName"], r["rarity"], float(r["chance"])) for r in relic["rewards"]]
            self._relics[key] = rewards
        # Die Seltenheit in der Quelle ist oft falsch; sie folgt aus der Chance im Intact-Zustand
        for (tier, name, state), rewards in self._relics.items():
            intact = {r.name: r.chance for r in self._relics.get((tier, name, "Intact"), [])}
            fixed = [Reward(r.name, rarity_for(intact.get(r.name), r.rarity), r.chance) for r in rewards]
            fixed.sort(key=lambda r: r.chance)
            self._relics[(tier, name, state)] = fixed

    @classmethod
    def load(cls) -> RelicDB:
        return cls(_cached_json("relics.json", RELICS_URL, RELIC_DATA_MAX_AGE))

    def rewards(self, tier: str, name: str, refinement: str = "Intact") -> list[Reward] | None:
        return self._relics.get((tier, name.upper(), refinement))

    def reward_names(self) -> list[str]:
        """Alle Teile, die aus irgendeinem Relikt kommen können."""
        return sorted({r.name for rewards in self._relics.values() for r in rewards})

    def names(self, tier: str | None = None) -> list[str]:
        """Sortierte Reliktnamen wie "Axi C12"."""
        found = {(t, n) for (t, n, _) in self._relics if tier in (None, t)}
        order = {t: i for i, t in enumerate(TIERS)}

        def sort_key(tn):
            t, n = tn
            letters = n.rstrip("0123456789")
            digits = n[len(letters):]
            return (order.get(t, 99), letters, int(digits) if digits else 0)

        return [f"{t} {n}" for t, n in sorted(found, key=sort_key)]


def price_from_orders(sell_orders: list[dict]) -> Price:
    plats = sorted(
        o["platinum"]
        for o in sell_orders
        if o.get("visible", True) and o.get("user", {}).get("status") in ("ingame", "online")
    )
    if not plats:
        return Price(None, None, 0, time.time())
    return Price(float(statistics.median(plats[:5])), plats[0], len(plats), time.time())


class Market:
    """Preise von warframe.market. Thread-sicher, mit Datei-Cache und Drosselung."""

    def __init__(self):
        raw = _cached_json("market_items.json", f"{MARKET_API}/items", ITEM_LIST_MAX_AGE)
        self._items: dict[str, dict] = {}
        for item in raw.get("data", []):
            name = item.get("i18n", {}).get("en", {}).get("name")
            if name:
                self._items[name.lower()] = item
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._cache_path = cache_dir() / "prices.json"
        try:
            self._prices: dict[str, dict] = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._prices = {}

    def item(self, name: str) -> dict | None:
        return self._items.get(name.lower())

    def prime_parts(self) -> dict[str, str | None]:
        """Alle handelbaren Prime-Teile, dazu gebaute Warframe-Teile.

        Ergebnis: Name -> None für handelbare Teile, oder Name -> Name der Blaupause
        für gebaute Teile (z. B. "Citrine Prime Chassis" aus "... Chassis Blueprint").
        Gebaute Warframe-Teile sind nicht handelbar.
        """
        parts: dict[str, str | None] = {}
        for item in self._items.values():
            tags = item.get("tags", [])
            name = item.get("i18n", {}).get("en", {}).get("name")
            if not name or "prime" not in tags or "set" in tags:
                continue
            if "component" not in tags and "blueprint" not in tags:
                continue
            parts[name] = None
            if "component" in tags and "blueprint" in tags and name.endswith(" Blueprint"):
                parts.setdefault(name.removesuffix(" Blueprint"), name)
        return parts

    def ducats(self, name: str) -> int | None:
        item = self.item(name)
        return item.get("ducats") if item else None

    def cached_price(self, name: str) -> Price | None:
        item = self.item(name)
        if not item:
            return None
        entry = self._prices.get(item["slug"])
        return Price(**entry) if entry else None

    def price(self, name: str, force: bool = False) -> Price | None:
        """Preis holen. None, wenn das Teil nicht handelbar ist (z. B. Forma)."""
        item = self.item(name)
        if not item:
            return None
        slug = item["slug"]
        cached = self.cached_price(name)
        if cached and not force and time.time() - cached.fetched < PRICE_MAX_AGE:
            return cached
        for attempt in range(MARKET_RETRIES):
            if attempt:
                time.sleep(1.5 * attempt)  # außerhalb der Sperre, andere Anfragen laufen weiter
            with self._lock:
                wait = self._last_request + MARKET_MIN_INTERVAL - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                try:
                    data = _http_json(f"{MARKET_API}/orders/item/{slug}/top")
                except (urllib.error.URLError, TimeoutError, ValueError):
                    continue
                finally:
                    self._last_request = time.monotonic()
                price = price_from_orders(data.get("data", {}).get("sell", []))
                self._prices[slug] = price.__dict__
                self._save_prices()
            return price
        return cached

    def _save_prices(self) -> None:
        tmp = self._cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._prices), encoding="utf-8")
        tmp.replace(self._cache_path)


def expected_value(rewards: list[Reward], values: dict[str, float | None]) -> float:
    """Erwarteter Wert einer Öffnung (Summe aus Chance mal Wert)."""
    return sum(r.chance / 100 * (values.get(r.name) or 0) for r in rewards)
