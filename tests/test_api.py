from fastapi.testclient import TestClient

from app.main import app


def test_items() -> None:
    client = TestClient(app)
    items = client.get("/api/items").json()
    assert items and {"id", "name", "price_level"} <= items[0].keys()
    assert client.get("/").status_code == 200


def test_feed_endpoint() -> None:
    client = TestClient(app)
    cards = client.get("/api/feed", params={"budget": 1, "now": "18:00", "liked": "food-1"}).json()
    assert cards and all(c["price_level"] == 1 for c in cards)
    assert client.get("/api/feed", params={"budget": 9}).status_code == 422
    assert client.get("/api/feed", params={"now": "6pm"}).status_code == 422
