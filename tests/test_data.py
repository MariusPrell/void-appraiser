from warframe_helper.data import RelicDB, Reward, expected_value, price_from_orders

RAW = {
    "relics": [
        {
            "tier": "Axi",
            "relicName": "C12",
            "state": "Radiant",
            "rewards": [
                {"itemName": "Forma Blueprint", "rarity": "Uncommon", "chance": 20},
                {"itemName": "Citrine Prime Neuroptics Blueprint", "rarity": "Rare", "chance": 10},
                {"itemName": "Kestrel Prime Blueprint", "rarity": "Common", "chance": 70},
            ],
        },
        {
            "tier": "Axi",
            "relicName": "C12",
            "state": "Intact",
            "rewards": [
                {"itemName": "Forma Blueprint", "rarity": "Uncommon", "chance": 11},
                {"itemName": "Citrine Prime Neuroptics Blueprint", "rarity": "Rare", "chance": 2},
                {"itemName": "Kestrel Prime Blueprint", "rarity": "Uncommon", "chance": 25.33},
            ],
        },
        {"tier": "Lith", "relicName": "A10", "state": "Intact", "rewards": []},
        {"tier": "Lith", "state": "Intact", "rewards": []},  # kaputter Eintrag
        {"tier": "Lith", "relicName": "A2", "state": "Intact", "rewards": []},
    ]
}


def _order(plat, status="ingame", visible=True):
    return {"platinum": plat, "visible": visible, "user": {"status": status}}


def test_relic_lookup_and_sorting():
    db = RelicDB(RAW)
    rewards = db.rewards("Axi", "c12", "Radiant")
    assert [r.name for r in rewards][0] == "Citrine Prime Neuroptics Blueprint"  # seltenste zuerst
    assert db.rewards("Axi", "C99", "Intact") is None
    # Seltenheit kommt aus der Intact-Chance, nicht aus der Quelle
    assert {r.name: r.rarity for r in rewards}["Kestrel Prime Blueprint"] == "Common"
    assert db.names() == ["Lith A2", "Lith A10", "Axi C12"]


def test_price_uses_only_online_sellers():
    orders = [_order(5, "offline"), _order(30), _order(10, "online"), _order(20), _order(1, visible=False)]
    price = price_from_orders(orders)
    assert price.lowest == 10
    assert price.median == 20
    assert price.offers == 3


def test_price_without_offers():
    assert price_from_orders([]).value is None


def test_expected_value():
    rewards = [Reward("A", "Rare", 10), Reward("B", "Common", 90)]
    assert expected_value(rewards, {"A": 100, "B": None}) == 10


def test_price_retries_after_errors(monkeypatch, tmp_path):
    import urllib.error

    from warframe_helper import data

    monkeypatch.setattr(data, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    items = {"data": [{"slug": "lex_prime_receiver", "ducats": 15, "i18n": {"en": {"name": "Lex Prime Receiver"}}}]}
    calls = []

    def fake_http(url, timeout=20):
        if url.endswith("/items"):
            return items
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)
        return {"data": {"sell": [_order(7), _order(9)]}}

    monkeypatch.setattr(data, "_http_json", fake_http)
    market = data.Market()
    price = market.price("Lex Prime Receiver")
    assert len(calls) == 3
    assert price.median == 8
