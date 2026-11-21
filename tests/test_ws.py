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


def test_brand_colour_becomes_readable_venue_colours() -> None:
    from app.colors import venue_colors

    red = venue_colors("#e4002b")
    assert red and set(red) == {"deep", "soft", "light"}
    assert red["deep"].startswith("#") and int(red["deep"][1:3], 16) > int(
        red["deep"][3:5], 16
    )  # still red
    assert venue_colors("not a colour") is None and venue_colors(None) is None


def test_categories_from_google_types() -> None:
    from app.categories import google_kind, tags_for

    comedy = google_kind(["comedy_club", "bar"], "comedy_club")
    assert comedy and (comedy.category, comedy.group, comedy.adult) == (
        "comedy",
        "Entertainment",
        True,
    )
    pub = google_kind(["pub", "restaurant"])
    assert pub and pub.group == "Drinks"
    park = google_kind(["park"])
    assert park and tags_for(park, outdoors=True) == ["outdoors"]
    assert google_kind(["shoe_store"]) is None


def test_picks_come_from_different_groups() -> None:
    from datetime import datetime

    now = datetime(2026, 11, 21, 18, 0)

    def card(i: str, group: str, match: int, rating: float) -> dict[str, Any]:
        return {
            "id": i,
            "name": i,
            "type": "activity",
            "tags": ["culture", "indoors"],
            "group": group,
            "category": "culture",
            "closes_at": "2026-11-21T23:00:00",
            "leave_by_at": "2026-11-21T21:50:00",
            "walk_mins": 5,
            "match": match,
            "reasons": [],
            "rating": rating,
            "lat": 0,
            "lng": 0,
        }

    rows = ws.to_rows(
        [
            card("t1", "Entertainment", 90, 4.0),
            card("t2", "Entertainment", 88, 4.9),
            card("f1", "Food", 70, 4.2),
            card("d1", "Drinks", 60, 4.6),
        ],
        now,
        raining=False,
    )
    picks = {r["pick"]: r["id"] for r in rows if r["pick"]}
    assert picks == {"best": "t1", "runner_up": "f1", "wildcard": "d1"}


def test_audit_fixes_for_categories() -> None:
    from app.categories import google_kind

    def group(types: list[str], primary: str = "") -> str | None:
        k = google_kind(types, primary)
        return k.group if k else None

    assert (
        group(["indian_restaurant", "bar", "restaurant"], "indian_restaurant") == "Food"
    )  # Dishoom
    assert group(["steak_house", "bar"], "steak_house") == "Food"  # Blacklock
    assert group(["bar", "miniature_golf_course"], "bar") == "Entertainment"  # Puttshack
    assert group(["bar", "karaoke"], "bar") == "Entertainment"  # Lucky Voice
    assert group(["irish_pub", "pub"], "irish_pub") == "Drinks"
    assert (
        group(["chicken_restaurant", "restaurant"], "chicken_restaurant") is None
    )  # Dave's Hot Chicken
    assert group(["university", "performing_arts_theater"]) is None  # Guildhall School
    assert group(["store"], "store") is None


def test_walk_in_places_have_no_time_and_bookable_ones_get_book() -> None:
    from datetime import datetime

    now = datetime(2026, 11, 21, 18, 0)
    base = {
        "type": "food_deal",
        "tags": ["food", "indoors"],
        "group": "Food",
        "category": "food",
        "opens": "11:00",
        "closes": "00:00",
        "closes_at": "2026-11-22T00:00:00",
        "leave_by_at": "2026-11-21T22:50:00",
        "walk_mins": 5,
        "match": 80,
        "reasons": [],
        "rating": 4.1,
        "lat": 0,
        "lng": 0,
        "url": "https://example.com",
    }
    food = ws.to_rows([{**base, "id": "dave", "name": "Chicken place"}], now, raining=False)[0]
    assert (food["timed"], food["departure_label"], food["booking_url"]) == (
        False,
        "Open till",
        None,
    )
    show = ws.to_rows(
        [
            {
                **base,
                "id": "show",
                "name": "A Theatre",
                "needs_booking": True,
                "group": "Entertainment",
            }
        ],
        now,
        raining=False,
    )[0]
    assert (
        show["needs_booking"] and show["booking_url"] == "https://example.com" and not show["timed"]
    )
