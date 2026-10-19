import time

from void_appraiser.logwatch import (
    LogWatcher,
    RelicEquipped,
    RewardScreenClosed,
    RewardScreenOpened,
    parse_line,
)

EQUIP_RADIANT = (
    "23690.029 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Are you sure you want "
    "to equip Axi C12 Relic [RADIANT] for this mission? It will be consumed if you seal the Void "
    "Fissure and extract., title= leftItem=/Menu/Confirm_Item_Yes, rightItem=/Menu/Confirm_Item_No)"
)
EQUIP_INTACT = (
    "24746.748 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Are you sure you want "
    "to equip Lith P1 Relic for this mission? It will be consumed if you seal the Void Fissure and "
    "extract., title= leftItem=/Menu/Confirm_Item_Yes, rightItem=/Menu/Confirm_Item_No)"
)
REFINE_EQUIP = (
    "24041.117 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Are you sure you want "
    "to refine and equip Meso S8 Relic? It will cost 100 Void Traces and the relic will be consumed "
    "if you seal the Void Fissure and extract., title= leftItem=/Menu/Confirm_Item_Yes)"
)
OPENED = "21358.850 Script [Info]: ProjectionRewardChoice.lua: Got rewards"
CLOSED = "21373.812 Script [Info]: ProjectionRewardChoice.lua: Relic reward screen shut down"


def test_parse_equip():
    assert parse_line(EQUIP_RADIANT) == RelicEquipped("Axi", "C12", "Radiant")
    assert parse_line(EQUIP_INTACT) == RelicEquipped("Lith", "P1", "Intact")
    assert parse_line(REFINE_EQUIP) == RelicEquipped("Meso", "S8", "Radiant")


def test_parse_reward_screen():
    assert parse_line(OPENED) == RewardScreenOpened()
    assert parse_line(CLOSED) == RewardScreenClosed()
    assert parse_line("21358.598 Script [Info]: ProjectionRewardChoice.lua: Pause countdown done") is None


def test_parse_ignores_refine_question():
    line = "22985.605 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Refine Axi C12 Relic to RADIANT? It will cost 100., title=)"
    assert parse_line(line) is None


def _wait_for(events, n, timeout=3):
    end = time.time() + timeout
    while len(events) < n and time.time() < end:
        time.sleep(0.05)


def test_watcher_reports_last_relic_then_follows(tmp_path):
    log = tmp_path / "EE.log"
    log.write_text("\n".join([EQUIP_INTACT, OPENED, CLOSED, EQUIP_RADIANT, ""]))
    events = []
    watcher = LogWatcher(log, events.append, poll=0.05)
    watcher.start()
    _wait_for(events, 1)
    # Vom alten Log nur das letzte Relikt, keine alten Bildschirm-Ereignisse
    assert events == [RelicEquipped("Axi", "C12", "Radiant")]

    with open(log, "a") as f:
        f.write(OPENED + "\n")
        f.write(CLOSED[:30])  # halbe Zeile: noch nicht melden
    _wait_for(events, 2)
    time.sleep(0.2)
    assert events[1:] == [RewardScreenOpened()]

    with open(log, "a") as f:
        f.write(CLOSED[30:] + "\n")
    _wait_for(events, 3)
    assert events[2:] == [RewardScreenClosed()]

    # Neues Spiel: Log wird neu angelegt und ist kürzer
    log.write_text(EQUIP_INTACT + "\n")
    _wait_for(events, 4)
    watcher.stop()
    assert events[3:] == [RelicEquipped("Lith", "P1", "Intact")]
