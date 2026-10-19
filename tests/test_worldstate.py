import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from void_appraiser.worldstate import parse, time_left

RAW = json.loads((Path(__file__).parent / "fixtures/worldstate.json").read_text())
NOW = datetime.fromisoformat(RAW["timestamp"].replace("Z", "+00:00"))


def test_fissure_kinds_and_order():
    ws = parse(RAW, NOW)
    assert {f.kind for f in ws.fissures} == {"Normal", "Steel Path", "Void Storm"}
    ranks = [f.tier_rank for f in ws.fissures]
    assert ranks == sorted(ranks)


def test_expired_entries_are_dropped():
    later = NOW + timedelta(days=1)
    ws = parse(RAW, later)
    assert ws.fissures == [] and ws.alerts == []


def test_cycles():
    ws = parse(RAW, NOW)
    places = {c.place: c.state for c in ws.cycles}
    assert places["Plains of Eidolon"] in ("Day", "Night")
    assert places["Orb Vallis"] in ("Warm", "Cold")
    assert "Duviri" in places


def test_alert_reward_text():
    alert = parse(RAW, NOW).alerts[0]
    assert "Credits" in alert.reward and "×" in alert.reward


def test_time_left():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert time_left(now + timedelta(hours=1, minutes=5), now) == "1h 05m"
    assert time_left(now + timedelta(minutes=4, seconds=9), now) == "4m 09s"
    assert time_left(now - timedelta(seconds=1), now) == "expired"
