from typing import Any

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
    assert cards and all(c["source"] == "Sample data" for c in cards)
    fits = [c["price_level"] == 1 for c in cards]
    assert fits == sorted(fits, reverse=True)  # within budget first, pricier ones after
    assert all(c["walk_mins"] >= 1 for c in cards)


def test_feed_validation() -> None:
    assert client.get("/api/feed", params={"budget": 9}).status_code == 422
    assert client.get("/api/feed", params={"now": "6pm"}).status_code == 422
    assert client.get("/api/feed", params={"now": "25:00"}).status_code == 422
    assert client.get("/api/feed", params={"now": "12:60"}).status_code == 422
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
    assert item["tags"] == ["games", "active", "indoors"] and item["price_level"] == 2
    assert (item["category"], item["group"]) == ("games", "Entertainment")
    sun_0030 = datetime(2026, 11, 22, 0, 30)  # still inside Saturday's late window
    assert (places.to_item(place, sun_0030) or {}).get("closes") == "01:00"
    assert places.to_item({**place, "regularOpeningHours": {}}, sat_8pm) is None


def test_place_photo_is_fresh_and_keeps_key_server_side(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    import httpx

    place_id = "demo-place"
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-server-key")
    monkeypatch.setattr(places, "_cache", {(0.0, 0.0): (time.time(), [{"id": place_id}])})
    calls: list[str] = []

    def get(url: str, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        assert kwargs["headers"]["X-Goog-Api-Key"] == "test-server-key"
        payload: dict[str, Any]
        if url.endswith("/media"):
            payload = {"photoUri": "https://lh3.googleusercontent.com/photo"}
        else:
            payload = {
                "photos": [
                    {"name": f"places/{place_id}/photos/small", "widthPx": 800},
                    {
                        "name": f"places/{place_id}/photos/large",
                        "widthPx": 1600,
                        "heightPx": 900,
                        "authorAttributions": [{"displayName": "Photo author"}],
                        "googleMapsUri": "https://maps.google.com/photo",
                    },
                ],
            }
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    assert client.get("/api/places/unknown/photo").status_code == 404
    response = client.get(f"/api/places/{place_id}/photo")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "url": "https://lh3.googleusercontent.com/photo",
        "authors": [{"displayName": "Photo author"}],
        "source_url": "https://maps.google.com/photo",
    }
    assert calls == [
        f"{places.API}/{place_id}",
        f"{places.API}/{place_id}/photos/large/media",
    ]
    assert places.featured_photo(place_id, {"index": 0, "width": 1600, "height": 900}) is None
    assert (
        places.featured_photo(place_id, {"index": 1, "width": 1600, "height": 900})
        == response.json()
    )
