import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import geo, osm, voice, ws
from app.main import app


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setattr(geo, "weather", lambda lat, lng: None)
    monkeypatch.setattr(osm, "nearby", lambda lat, lng: [])


def recv(sock: Any, kind: str) -> dict[str, Any]:
    while True:
        msg: dict[str, Any] = json.loads(sock.receive_text())
        if msg["type"] == kind:
            return msg


def test_smoke_flow_from_integration_guide() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as sock:
        # The start screen sends prefs and typed text before join.
        sock.send_text(
            json.dumps(
                {
                    "type": "prefs",
                    "budget": 20,
                    "student": True,
                    "adult": False,
                    "include": [],
                    "exclude": [],
                    "company": 1,
                }
            )
        )
        sock.send_text(
            json.dumps({"type": "talk_text", "text": "something chill, nothing outdoors"})
        )
        chips = recv(sock, "chips")
        assert "chill" in chips["include"] and "outdoors" in chips["exclude"]

        sock.send_text(json.dumps({"type": "join", "room": None}))
        assert recv(sock, "joined")["room"]
        recv(sock, "board")  # sent straight after join
        sock.send_text(json.dumps({"type": "time_travel", "now": "2026-11-21T18:00:00+00:00"}))
        board = recv(sock, "board")
        rows = board["rows"]
        assert rows and board["count"] == sum(
            r["status"] not in ("departed", "cancelled") for r in rows
        )
        assert sum(r["pick"] == "best" for r in rows) == 1
        row = rows[0]
        assert row["departure_time"].endswith(("+00:00", "+01:00")) and 0 <= row["score"] <= 10
        assert all(
            r["status"] in ("on_time", "boarding", "last_call", "departed", "delayed_rain")
            for r in rows
        )
        assert len(row["reasons"]) <= 3 and all("icon" in x for x in row["reasons"])

        # "Not for me" removes a place from the board.
        sock.send_text(json.dumps({"type": "feedback", "item_id": row["id"], "kind": "skip"}))
        assert row["id"] not in {r["id"] for r in recv(sock, "board")["rows"]}


def test_voice_audio_becomes_chips(monkeypatch: pytest.MonkeyPatch) -> None:
    got: dict[str, Any] = {}

    def fake(audio: bytes, mime: str, context: dict[str, Any]) -> dict[str, Any]:
        got["mime"], got["wav"] = mime, audio[:4]
        return {
            "budget": 1,
            "include_tags": ["active"],
            "exclude_tags": ["nightlife"],
            "reply": "Cheap and active.",
        }

    monkeypatch.setattr(voice, "audio_to_filters", fake)
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "talk_start", "purpose": "mood"}))
        sock.send_bytes(b"\x00\x00" * 1600)  # 100 ms of PCM16 silence
        sock.send_text(json.dumps({"type": "talk_end"}))
        chips = recv(sock, "chips")
        assert chips == {"type": "chips", "include": ["active"], "exclude": ["clubs"], "budget": 10}
        assert recv(sock, "note")["text"] == "Cheap and active."
    assert got == {"mime": "audio/wav", "wav": b"RIFF"}


def test_voice_failure_is_friendly(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any) -> dict[str, Any]:
        raise voice.VoiceError("boom")

    monkeypatch.setattr(voice, "audio_to_filters", broken)
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "talk_start", "purpose": "mood"}))
        sock.send_bytes(b"\x00\x00" * 160)
        sock.send_text(json.dumps({"type": "talk_end"}))
        assert recv(sock, "chips")["include"] == []
        assert "typing" in recv(sock, "note")["text"]


def test_text_to_chips() -> None:
    assert ws.text_to_chips("cheap, active, no clubs") == {
        "include": ["active"],
        "exclude": ["clubs"],
        "budget": 10,
    }
