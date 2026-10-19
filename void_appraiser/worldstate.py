"""Aktueller Spielzustand (Worldstate) von der Fan-API api.warframestat.us.

Liefert Void Fissures (normal, Steel Path, Void Storm), Alerts und die
Tageszeiten der offenen Welten. Ein Abruf liefert alles auf einmal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .data import _http_json

WORLDSTATE_URL = "https://api.warframestat.us/pc/?language=en"
TIER_ORDER = {"Lith": 1, "Meso": 2, "Neo": 3, "Axi": 4, "Requiem": 5, "Omnia": 6}

# (API-Schlüssel, angezeigter Name, Übersetzung der Zustände)
CYCLES = [
    ("cetusCycle", "Plains of Eidolon", {"day": "Tag", "night": "Nacht"}),
    ("vallisCycle", "Orb Vallis", {"warm": "Warm", "cold": "Kalt"}),
    ("cambionCycle", "Cambion Drift", {"fass": "Fass", "vome": "Vome"}),
    ("zarimanCycle", "Zariman", {"corpus": "Corpus", "grineer": "Grineer"}),
    ("duviriCycle", "Duviri", {}),
]


@dataclass(frozen=True)
class Fissure:
    tier: str
    mission: str
    node: str
    enemy: str
    steel_path: bool
    void_storm: bool
    expiry: datetime

    @property
    def kind(self) -> str:
        if self.void_storm:
            return "Void Storm"
        return "Steel Path" if self.steel_path else "Normal"

    @property
    def tier_rank(self) -> int:
        return TIER_ORDER.get(self.tier, 99)


@dataclass(frozen=True)
class Cycle:
    place: str
    state: str
    expiry: datetime


@dataclass(frozen=True)
class Alert:
    mission: str
    node: str
    faction: str
    levels: str
    reward: str
    expiry: datetime


@dataclass(frozen=True)
class Worldstate:
    fissures: list[Fissure]
    cycles: list[Cycle]
    alerts: list[Alert]
    fetched: datetime


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _reward_text(reward: dict) -> str:
    parts = [f"{i['count']}× {i['type']}" for i in reward.get("countedItems") or []]
    parts += list(reward.get("items") or [])
    if reward.get("credits"):
        parts.append(f"{reward['credits']:,} Credits".replace(",", "."))
    return ", ".join(parts) or reward.get("asString", "")


def parse(raw: dict, now: datetime | None = None) -> Worldstate:
    now = now or datetime.now(timezone.utc)
    fissures = []
    for f in raw.get("fissures") or []:
        expiry = _time(f.get("expiry"))
        if expiry is None or expiry <= now or f.get("expired"):
            continue
        fissures.append(
            Fissure(
                tier=f.get("tier", "?"),
                mission=f.get("missionType", "?"),
                node=f.get("node", "?"),
                enemy=f.get("enemy", "?"),
                steel_path=bool(f.get("isHard")),
                void_storm=bool(f.get("isStorm")),
                expiry=expiry,
            )
        )
    fissures.sort(key=lambda f: (f.tier_rank, f.expiry))

    cycles = []
    for key, place, states in CYCLES:
        c = raw.get(key) or {}
        expiry = _time(c.get("expiry"))
        if expiry and c.get("state"):
            cycles.append(Cycle(place, states.get(c["state"], c["state"].capitalize()), expiry))

    alerts = []
    for a in raw.get("alerts") or []:
        m = a.get("mission") or {}
        expiry = _time(a.get("expiry"))
        if expiry is None or expiry <= now:
            continue
        lo, hi = m.get("minEnemyLevel"), m.get("maxEnemyLevel")
        alerts.append(
            Alert(
                mission=m.get("type", "?"),
                node=m.get("node", "?"),
                faction=m.get("faction", "?"),
                levels=f"{lo}–{hi}" if lo is not None and hi is not None and lo != hi else str(lo or hi or "?"),
                reward=_reward_text(m.get("reward") or {}),
                expiry=expiry,
            )
        )
    alerts.sort(key=lambda a: a.expiry)
    return Worldstate(fissures, cycles, alerts, now)


def fetch() -> Worldstate:
    return parse(_http_json(WORLDSTATE_URL))


def time_left(expiry: datetime, now: datetime | None = None) -> str:
    """Restzeit kurz und lesbar, z. B. "1h 05m" oder "4m 09s"."""
    now = now or datetime.now(timezone.utc)
    seconds = int((expiry - now).total_seconds())
    if seconds <= 0:
        return "abgelaufen"
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"
