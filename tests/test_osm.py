from datetime import datetime
from typing import Any

from app.osm import hours_on, to_item

MON, SAT, SUN = 0, 5, 6


def test_hours_on_common_forms() -> None:
    spec = "Mo-Fr 09:00-17:00; Sa 10:00-16:00; Su off"
    assert hours_on(spec, MON) == [("09:00", "17:00")]
    assert hours_on(spec, SAT) == [("10:00", "16:00")]
    assert hours_on(spec, SUN) == []
    assert hours_on("24/7", SUN) == [("00:00", "00:00")]
    assert hours_on("12:00-15:00,18:00-24:00", SUN) == [("12:00", "15:00"), ("18:00", "23:59")]
    assert hours_on("Fr-Mo 18:00-02:00", SUN) == [("18:00", "02:00")]  # wraps the week
    assert hours_on("Mo-Fr 09:00-17:00; PH off", MON) is None  # holidays: unsupported, skip
    assert hours_on("Mo-Fr sunrise-sunset", MON) is None


def test_to_item() -> None:
    el: dict[str, Any] = {
        "type": "node",
        "id": 42,
        "lat": 51.5,
        "lon": -0.1,
        "tags": {"name": "Lanes", "leisure": "bowling_alley", "opening_hours": "Mo-Su 12:00-02:00"},
    }
    sat_8pm = datetime(2026, 11, 21, 20, 0)
    item = to_item(el, sat_8pm)
    assert (
        item
        and item["id"] == "osm-node-42"
        and (item["opens"], item["closes"]) == ("12:00", "02:00")
    )
    assert item["tags"] == ["games", "active", "indoors"] and item["rating"] is None
    assert (item["category"], item["group"]) == ("games", "Entertainment")
    assert to_item(el, datetime(2026, 11, 22, 1, 0))  # 1am: still in Saturday's late window
    shut = {**el, "tags": {**el["tags"], "opening_hours": "Mo-Su 09:00-17:00"}}
    assert to_item(shut, sat_8pm) is None  # already closed today
    assert (
        to_item({**el, "tags": {"name": "X", "shop": "bakery", "opening_hours": "24/7"}}, sat_8pm)
        is None
    )
