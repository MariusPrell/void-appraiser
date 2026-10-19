"""Liest das Warframe-Log (EE.log) mit und meldet Relikt-Ereignisse.

Erkannt wird (nur englischer Spielclient):
- welches Relikt ausgerüstet wird, samt Veredelung
- wann der Belohnungsbildschirm aufgeht und wieder zugeht
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_EQUIP = re.compile(
    r"Are you sure you want to equip ([A-Z][a-z]+) (\w+) Relic"
    r"(?: \[(EXCEPTIONAL|FLAWLESS|RADIANT)\])? for this mission"
)
# "Refine and equip" nennt die Stufe nicht, aber die Kosten in Void Traces
_REFINE_EQUIP = re.compile(
    r"Are you sure you want to refine and equip ([A-Z][a-z]+) (\w+) Relic\?"
    r" It will cost (\d+) Void Traces"
)
_REFINE_COST = {25: "Exceptional", 50: "Flawless", 100: "Radiant"}
_REWARDS_SHOWN = "ProjectionRewardChoice.lua: Got rewards"
_REWARDS_CLOSED = "ProjectionRewardChoice.lua: Relic reward screen shut down"


@dataclass(frozen=True)
class RelicEquipped:
    tier: str
    name: str
    refinement: str  # Intact, Exceptional, Flawless, Radiant


@dataclass(frozen=True)
class RewardScreenOpened:
    pass


@dataclass(frozen=True)
class RewardScreenClosed:
    pass


Event = RelicEquipped | RewardScreenOpened | RewardScreenClosed


def parse_line(line: str) -> Event | None:
    if "Dialog::CreateOkCancel" in line:
        if m := _EQUIP.search(line):
            return RelicEquipped(m[1], m[2].upper(), (m[3] or "Intact").capitalize())
        if m := _REFINE_EQUIP.search(line):
            return RelicEquipped(m[1], m[2].upper(), _REFINE_COST.get(int(m[3]), "Intact"))
    elif _REWARDS_SHOWN in line:
        return RewardScreenOpened()
    elif _REWARDS_CLOSED in line:
        return RewardScreenClosed()
    return None


class LogWatcher:
    """Folgt dem Log in einem Hintergrund-Thread (wie `tail -f`).

    Beim Start wird das vorhandene Log einmal gelesen, damit das zuletzt
    ausgerüstete Relikt bekannt ist. Bildschirm-Ereignisse aus der
    Vergangenheit werden dabei nicht gemeldet.
    """

    def __init__(self, path: Path, on_event: Callable[[Event], None], poll: float = 0.5):
        self.path = path
        self.on_event = on_event
        self.poll = poll
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="LogWatcher", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        pos = 0
        identity = None
        first = True
        buf = b""
        while not self._stop.is_set():
            try:
                st = self.path.stat()
            except OSError:
                self._stop.wait(2)
                continue
            # Warframe legt das Log bei jedem Spielstart neu an
            new_identity = (st.st_ino, st.st_dev) if st.st_ino else None
            if st.st_size < pos or (identity and new_identity != identity):
                pos, buf = 0, b""
            identity = new_identity
            if st.st_size > pos:
                with open(self.path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read(st.st_size - pos)
                pos += len(chunk)
                buf += chunk
                *lines, buf = buf.split(b"\n")
                last_relic = None
                for raw in lines:
                    event = parse_line(raw.decode("utf-8", errors="replace"))
                    if event is None:
                        continue
                    if first:
                        if isinstance(event, RelicEquipped):
                            last_relic = event
                    else:
                        self.on_event(event)
                if first and last_relic:
                    self.on_event(last_relic)
            first = False
            self._stop.wait(self.poll)


def follow_once(path: Path) -> list[Event]:
    """Alle Ereignisse eines Logs auf einmal (für Tests und Fehlersuche)."""
    with open(path, "rb") as f:
        return [e for raw in f if (e := parse_line(raw.decode("utf-8", errors="replace")))]


if __name__ == "__main__":
    import sys

    from .paths import find_log

    log = Path(sys.argv[1]) if len(sys.argv) > 1 else find_log()
    print("Log:", log)
    watcher = LogWatcher(log, lambda e: print(time.strftime("%H:%M:%S"), e))
    watcher.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
