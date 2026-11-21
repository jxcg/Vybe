from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import geo, osm, voice
from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setattr(geo, "weather", lambda lat, lng: None)
    monkeypatch.setattr(osm, "nearby", lambda lat, lng: [])
    return TestClient(app)


def test_board_poll_carries_its_own_state(client: TestClient) -> None:
    body = {"now": "2026-11-21T18:45:00Z"}
    first = client.post("/api/board", json=body)
    assert first.status_code == 200
    board = first.json()
    assert board["type"] == "board"
    excluded = board["rows"][0]["id"]
    filtered = client.post("/api/board", json={**body, "skipped": [excluded]}).json()
    assert excluded not in {row["id"] for row in filtered["rows"]}
    fresh = client.post("/api/board", json=body).json()
    assert excluded in {row["id"] for row in fresh["rows"]}


def test_suggestions_work_before_join(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    typed = client.post("/api/chips", json={"text": "cheap food"})
    assert typed.json()[-1] == {"type": "chips", "include": ["food"], "exclude": [], "budget": 10}
    voxtral = Mock(return_value={"include_tags": ["food"]})
    monkeypatch.setattr(voice, "audio_to_filters", voxtral)
    spoken = client.post("/api/voice", content=b"clip", headers={"content-type": "audio/webm"})
    assert spoken.json()[0]["include"] == ["food"]
    assert voxtral.call_args.args[:2] == (b"clip", "audio/webm")
