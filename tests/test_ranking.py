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
    assert got["climb-1"]["over_budget"]  # £££ on a ££ budget: still an option…
    ordered = [c["id"] for c in rank(load_items(), at(18), budget=2, adult=False)]
    assert ordered[-1] == "climb-1"  # …but ranked after everything within budget
    assert "Pricier than your budget" in got["climb-1"]["reasons"]
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
    assert cold["bowl-1"]["match"] > nice["bowl-1"]["match"]  # cold favours indoors too
    assert "Nice out" in nice["park-1"]["reasons"]
    assert nice["park-1"]["rating"] == 4.2  # Google rating passes through untouched


def test_likes_ignore_indoors_and_24h_stays_open() -> None:
    liked = by_id(rank(load_items(), at(18), liked=frozenset({"museum-1"})))  # culture, indoors
    assert "Matches your likes" not in liked["bowl-1"]["reasons"]  # active: only shares indoors
    allday = {**load_items()[0], "id": "x", "opens": "00:00", "closes": "00:00"}
    assert by_id(rank([allday], at(23, 50)))["x"]["badge"] == "plenty"


def test_personal_fit_from_reviews_and_guesses() -> None:
    items = load_items()
    plain = by_id(rank(items, at(19)))
    # Review data from the pipeline: a strong 18-21 audience earns a reason and a higher match
    reviewed = [{**i, "audience": {"18-21": 0.9}} if i["id"] == "bowl-1" else i for i in items]
    young = by_id(rank(reviewed, at(19), age="18-21"))
    assert young["bowl-1"]["match"] > plain["bowl-1"]["match"]
    assert "Popular with 18–21s" in young["bowl-1"]["reasons"]  # noqa: RUF001
    # Without review data it's only a nudge: no "Popular with" claim
    guessed = by_id(rank(items, at(19), age="18-21"))
    assert not any(r.startswith("Popular with") for c in guessed.values() for r in c["reasons"])
    # Vibe: lively favours nightlife over a museum
    lively = by_id(rank(items, at(19), vibe="lively"))
    chill = by_id(rank(items, at(19), vibe="chill"))
    assert lively["comedy-1"]["match"] - lively["museum-1"]["match"] > (
        chill["comedy-1"]["match"] - chill["museum-1"]["match"]
    )
    # Groups: only claimed when the data says so
    grouped = [{**i, "good_for_groups": True} if i["id"] == "food-1" else i for i in items]
    assert "Good for groups" in by_id(rank(grouped, at(19), company=4))["food-1"]["reasons"]


def test_student_price_reason_stays_in_top_three() -> None:
    items = load_items()
    cards = {c["id"]: c for c in rank(items, at(18), student=True)}
    assert "Student price" in cards["bowl-1"]["reasons"]  # student_price: true in the fixture
    assert cards["bowl-1"]["match"] > {c["id"]: c for c in rank(items, at(18))}["bowl-1"]["match"]
    assert "Student price" not in cards["comedy-1"]["reasons"]
