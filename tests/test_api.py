from fastapi.testclient import TestClient

from app.main import app


def test_items_and_db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as client:
        items = client.get("/api/items").json()
        assert items and {"id", "name", "price_level"} <= items[0].keys()
        assert client.get("/").status_code == 200
    assert (tmp_path / "test.db").exists()
