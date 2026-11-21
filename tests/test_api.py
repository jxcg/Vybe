import pytest
from fastapi.testclient import TestClient

from app import geo, osm, places
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setattr(geo, "weather", lambda lat, lng: None)
    monkeypatch.setattr(osm, "nearby", lambda lat, lng: [])
    monkeypatch.setattr(osm, "geocode", lambda q: None)


def test_index() -> None:
    assert client.get("/").status_code == 200


def test_feed_uses_samples_without_key() -> None:
    cards = client.get("/api/feed", params={"budget": 1, "now": "18:00"}).json()
    assert cards and all(c["price_level"] == 1 and c["source"] == "Sample data" for c in cards)
    assert all(c["walk_mins"] >= 1 for c in cards)


def test_feed_validation() -> None:
    assert client.get("/api/feed", params={"budget": 9}).status_code == 422
    assert client.get("/api/feed", params={"now": "6pm"}).status_code == 422
    assert client.get("/api/feed", params={"lat": 200}).status_code == 422


def test_geocode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geo, "geocode_postcode", lambda q: (51.5, -0.09) if q == "SE1" else None)
    assert client.get("/api/geocode", params={"q": "SE1"}).json() == {"lat": 51.5, "lng": -0.09}
    assert client.get("/api/geocode", params={"q": "nowhere"}).status_code == 404


def test_places_mapping() -> None:
    from datetime import datetime

    sat_8pm = datetime(2026, 11, 21, 20, 0)  # Saturday = Google day 6
    place = {
        "id": "abc",
        "_kind": "activity",
        "displayName": {"text": "Real Bowling"},
        "location": {"latitude": 51.5, "longitude": -0.1},
        "types": ["bowling_alley"],
        "rating": 4.4,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "regularOpeningHours": {
            "periods": [
                {
                    "open": {"day": 6, "hour": 12, "minute": 0},
                    "close": {"day": 6, "hour": 15, "minute": 0},
                },
                {
                    "open": {"day": 6, "hour": 18, "minute": 0},
                    "close": {"day": 0, "hour": 1, "minute": 0},
                },
            ]
        },
    }
    item = places.to_item(place, sat_8pm)
    assert item and (item["opens"], item["closes"]) == ("18:00", "01:00")
    assert item["tags"] == ["active", "indoors"] and item["price_level"] == 2
    sun_0030 = datetime(2026, 11, 22, 0, 30)  # still inside Saturday's late window
    assert (places.to_item(place, sun_0030) or {}).get("closes") == "01:00"
    assert places.to_item({**place, "regularOpeningHours": {}}, sat_8pm) is None
