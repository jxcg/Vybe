import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.geo import Weather
from app.ranking import rank


def load_items() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(
        (Path(__file__).parent / "items_fixture.json").read_text()
    )
    return data


def at(hour: int, minute: int = 0, day: int = 21) -> datetime:
    return datetime(2026, 11, day, hour, minute)


def by_id(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in cards}


def test_filters() -> None:
    got = by_id(rank(load_items(), at(18), budget=2, adult=False))
    assert "coffee-1" not in got  # closes 19:00: no time for a 60 min visit plus the walk
    assert "climb-1" not in got  # £££ is over budget
    assert "comedy-1" not in got  # 18+
    assert "pizza-1" in got  # opens 21:00, exactly 3 hours ahead
    assert "pizza-1" not in by_id(rank(load_items(), at(17)))  # 4 hours ahead


def test_badges_sorting_and_shape() -> None:
    cards = rank(load_items(), at(19))
    got = by_id(cards)
    assert got["museum-1"]["badge"] == "soon"  # leave by 19:40
    assert got["bowl-1"]["badge"] == "plenty"  # leave by 21:48
    assert by_id(rank(load_items(), at(19, 30)))["museum-1"]["badge"] == "last"
    assert [c["match"] for c in cards] == sorted((c["match"] for c in cards), reverse=True)
    for c in cards:
        assert 0 <= c["match"] <= 100 and len(c["reasons"]) == 3


def test_after_midnight_window() -> None:
    got = by_id(rank(load_items(), at(0, 0, day=22)))
    assert "pizza-1" in got  # 21:00-02:00, leave by 00:50
    assert "comedy-1" not in got  # closes 01:00, leave by 23:45 has passed


def test_like_boosts_similar() -> None:
    base = by_id(rank(load_items(), at(18)))
    liked = by_id(rank(load_items(), at(18), liked=frozenset({"bowl-1"})))
    assert liked["climb-1"]["match"] > base["climb-1"]["match"]  # shares "active"
    assert "Matches your likes" in liked["climb-1"]["reasons"]


def test_rain_sinks_outdoor_places() -> None:
    dry = by_id(rank(load_items(), at(12)))
    wet = by_id(rank(load_items(), at(12), weather=Weather(raining=True, temp_c=12)))
    cold = by_id(rank(load_items(), at(12), weather=Weather(raining=False, temp_c=3)))
    nice = by_id(rank(load_items(), at(12), weather=Weather(raining=False, temp_c=20)))
    assert wet["park-1"]["match"] < dry["park-1"]["match"] < nice["park-1"]["match"]
    assert wet["bowl-1"]["match"] > nice["bowl-1"]["match"]
    assert "Indoors, it's raining" in wet["bowl-1"]["reasons"]
    assert "Indoors, it's cold" in cold["bowl-1"]["reasons"]
    assert "Nice out" in nice["park-1"]["reasons"]
    assert nice["park-1"]["rating"] == 4.2  # Google rating passes through untouched
