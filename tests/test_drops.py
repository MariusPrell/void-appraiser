import json
from pathlib import Path

from void_appraiser.drops import DropTable

RAW = json.loads((Path(__file__).parent / "fixtures/drops.json").read_text())


def test_search_words_in_any_order():
    table = DropTable(RAW)
    hits, total = table.search("gauss neuroptics")
    assert hits and all("Gauss Prime Neuroptics" in d.item for d in hits)
    assert total == len(hits)
    # Veredelte Relikte sind standardmäßig ausgeblendet
    assert all("(Radiant)" not in d.place for d in hits)
    all_hits, _ = table.search("neuroptics GAUSS", hide_refined=False)
    assert len(all_hits) > len(hits)


def test_sorted_by_chance_and_parsed():
    table = DropTable(RAW)
    hits, _ = table.search("gauss", hide_refined=False)
    chances = [d.chance for d in hits]
    assert chances == sorted(chances, reverse=True)
    assert all("<b>" not in d.place for d in table.drops)
    assert any(d.chance is None for d in table.drops)  # "chance": null bleibt erlaubt


def test_relic_place():
    table = DropTable(RAW)
    hits, _ = table.search("gauss neuroptics", hide_refined=False)
    relics = {d.relic for d in hits if d.relic}
    assert any(r[2] == "Radiant" for r in relics) and any(r[2] == "Intact" for r in relics)


def test_search_in_places():
    table = DropTable(RAW)
    hits, _ = table.search("apollodorus", in_places=True)
    assert hits and all("Apollodorus" in d.place for d in hits)
    assert table.search("   ")[0] == []
