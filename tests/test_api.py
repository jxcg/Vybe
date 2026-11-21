from fastapi.testclient import TestClient

from app.main import app


def test_items() -> None:
    client = TestClient(app)
    items = client.get("/api/items").json()
    assert items and {"id", "name", "price_level"} <= items[0].keys()
    assert client.get("/").status_code == 200
