import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import geo, osm, rooms, voice, ws
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


@pytest.mark.parametrize(
    ("utterance", "matches"),
    [
        ("pizza and a comedy show", {"pizza", "comedy", "ambiguous"}),
        ("pizza and music", {"pizza", "gig"}),
        ("I fancy ice cream", {"dessert"}),
        ("sushi and karaoke", {"sushi", "karaoke"}),
        ("pottery class", {"pottery"}),
        (
            "Have a laugh and laugh and eat food",
            {"pizza", "restaurant", "dessert", "sushi", "comedy", "ambiguous"},
        ),
        ("Have a laugh", {"comedy", "ambiguous"}),
        ("I want to dance tonight", {"nightclub", "dance"}),
        ("let's go out dancing, no clubs", {"dance"}),
        ("I want to sing tonight", {"karaoke"}),
        ("I want to watch a movie", {"cinema"}),
        ("I want to climb", {"climbing"}),
        ("dance or sushi under £10", {"nightclub", "sushi"}),
    ],
)
def test_specific_requests_match_venue_evidence(
    monkeypatch: pytest.MonkeyPatch, utterance: str, matches: set[str]
) -> None:
    from datetime import datetime

    from app.main import items_near

    now = datetime(2026, 11, 21, 18)
    sample = items_near(51.51, -0.13, now)[0]
    items = [
        dict(
            sample,
            id=i,
            name=name,
            group=group,
            tags=tags,
            interest_terms=terms,
            opens="10:00",
            closes="23:00",
        )
        for i, name, group, tags, terms in (
            ("pizza", "A pizzeria", "Food", ["food"], ["pizza_restaurant"]),
            ("restaurant", "Dishoom", "Food", ["food"], ["indian_restaurant"]),
            ("dessert", "A dessert shop", "Food", ["food"], ["ice_cream_shop"]),
            ("sushi", "Sakana", "Food", ["food"], ["sushi_restaurant"]),
            ("comedy", "A stand-up show", "Entertainment", ["comedy"], []),
            ("gig", "A concert venue", "Entertainment", ["music"], ["concert_hall"]),
            ("karaoke", "Lucky Voice", "Entertainment", ["games"], ["karaoke"]),
            ("pottery", "Soho Pottery Classes", "Culture", ["culture"], []),
            ("cinema", "Picturehouse", "Entertainment", ["film", "culture"], []),
            ("nightclub", "Fabric", "Drinks", ["club", "nightlife"], ["night_club"]),
            ("dance", "Late Dance Studio", "Entertainment", ["active"], ["dance"]),
            ("pub", "The Soho Pub", "Drinks", ["nightlife"], ["pub"]),
            ("climbing", "The Arch", "Entertainment", ["active"], ["climbing"]),
            ("ambiguous", "Another Comedy Club", "Entertainment", ["comedy", "nightlife"], []),
        )
    ]
    for item in items:
        item["price"] = {"nightclub": 8, "sushi": 7, "dance": 15}.get(item["id"])
    monkeypatch.setattr("app.main.items_near", lambda *args: items)
    monkeypatch.setattr(ws.Session, "now", lambda _: now)
    for spoken in (False, True):
        monkeypatch.setattr(voice, "audio_to_filters", lambda *_: {"transcript": utterance})
        with TestClient(app).websocket_connect("/ws") as sock:
            sock.send_json({"type": "join"})
            recv(sock, "board")
            if spoken:
                sock.send_json({"type": "talk_start"})
                sock.send_bytes(b"\x00\x30" * 160)
                sock.send_json({"type": "talk_end"})
            else:
                sock.send_json({"type": "talk_text", "text": utterance})
            chips = recv(sock, "chips")
            prefs = {
                "type": "prefs",
                "include": ["food"],
                "requested": chips.get("requested", []),
                "exclude": chips["exclude"],
                "budget": chips.get("budget", 999),
            }
            sock.send_json(prefs)
            board = recv(sock, "board")
            assert board["group"] is None
            assert {row["id"] for row in board["rows"]} == matches
            original = items[:]
            items[:] = [item for item in items if item["id"] == "pub"]
            sock.send_json(prefs)
            assert recv(sock, "board")["rows"] == []
            items[:] = original
            sock.send_json(
                {"type": "prefs", "include": [], "exclude": [], "requested": [], "budget": 999}
            )
            assert {row["id"] for row in recv(sock, "board")["rows"]} == {
                item["id"] for item in items
            }


def test_food_and_comedy_keep_both_groups_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from app.main import items_near

    now = datetime(2026, 11, 21, 18)
    sample = items_near(51.51, -0.13, now)[0]
    items = [
        dict(sample, id="food", group="Food", tags=["food"], opens="10:00", closes="23:00"),
        dict(
            sample,
            id="comedy",
            group="Entertainment",
            tags=["comedy"],
            opens="10:00",
            closes="23:00",
        ),
        dict(
            sample, id="cinema", group="Entertainment", tags=["film"], opens="10:00", closes="23:00"
        ),
    ]
    monkeypatch.setattr("app.main.items_near", lambda *args: items)
    monkeypatch.setattr(ws.Session, "now", lambda _: now)
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "join"})
        recv(sock, "board")
        sock.send_json({"type": "talk_text", "text": "I want to have a laugh and eat food"})
        chips = recv(sock, "chips")
        sock.send_json(
            {
                "type": "prefs",
                "include": [tag for tag in chips["include"] if tag in rooms.INTO],
                "requested": chips["requested"],
            }
        )
        board = recv(sock, "board")
        assert board["group"] is None
        assert {row["id"] for row in board["rows"]} == {"food", "comedy"}


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
        sock.send_bytes(b"\x00\x30" * 1600)  # 100 ms of a loud PCM16 tone
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
        sock.send_bytes(b"\x00\x30" * 160)
        sock.send_text(json.dumps({"type": "talk_end"}))
        assert recv(sock, "chips")["include"] == []
        assert "typing" in recv(sock, "note")["text"]


def test_typed_text_uses_the_parser() -> None:
    from app.request_parse import parse_request

    assert parse_request("cheap, active, no clubs") == {
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


def test_voiceover_paths_become_served_urls(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "VOICEOVERS", tmp_path)
    (tmp_path / "abc.mp3").write_bytes(b"ID3")
    assert ws._voiceover_url("data/voiceovers/abc.mp3") == "/voiceovers/abc.mp3"
    assert (
        ws._voiceover_url("data/voiceovers/missing.mp3") is None
    )  # never link a file that isn't there
    assert ws._voiceover_url(None) is None


def test_silent_audio_skips_voxtral(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[int] = []

    def fake(*_: Any) -> dict[str, Any]:
        called.append(1)
        return {}

    monkeypatch.setattr(voice, "audio_to_filters", fake)
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "talk_start", "purpose": "mood"}))
        sock.send_bytes(b"\x00\x00" * 1600)  # silence
        sock.send_text(json.dumps({"type": "talk_end"}))
        assert recv(sock, "chips")["include"] == []
        assert "catch" in recv(sock, "note")["text"]
    assert not called  # never sent to Voxtral


def test_cached_card_photo_requires_credit(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    card = {
        "id": "venue",
        "name": "Venue",
        "tags": ["food"],
        "closes_at": "2026-11-21T22:00:00",
        "leave_by_at": "2026-11-21T21:50:00",
        "walk_mins": 5,
        "match": 80,
        "reasons": [],
        "rating": None,
        "lat": 0,
        "lng": 0,
    }
    cached = {
        "mode": "photo",
        "image_url": "https://venue.example/photo.jpg",
        "image_credit": "venue.example",
        "base": "#493424",
    }
    monkeypatch.setattr(ws, "_enriched", lambda: {"venue": {"theme": cached}})
    now = datetime(2026, 11, 21, 18)
    row = ws.to_rows([card], now, raining=False)[0]
    assert row["photo_url"] == cached["image_url"]
    assert row["photo_credit"] == cached["image_credit"]
    assert row["colors"] is not None

    del cached["image_credit"]
    row = ws.to_rows([card], now, raining=False)[0]
    assert row["photo_url"] is None
    assert row["photo_credit"] is None
    assert row["colors"] is not None


@pytest.mark.parametrize(
    ("interest", "group"),
    [
        ("food", "Food"),
        ("a laugh", "Entertainment"),
        ("active", "Entertainment"),
        ("competitive", "Entertainment"),
        ("live music", "Entertainment"),
        ("chill", "Culture"),
        ("culture", "Culture"),
        ("late night", "Drinks"),
    ],
)
def test_saved_interest_selects_available_group(
    monkeypatch: pytest.MonkeyPatch, interest: str, group: str
) -> None:
    from datetime import datetime

    from app.main import items_near

    sample = items_near(51.51, -0.13, datetime(2026, 11, 21, 18))[0]
    items = [
        dict(sample, id=str(i), group=name, opens="10:00", closes="23:00", adult_only=False)
        for i, name in enumerate(("Food", "Entertainment", "Culture", "Drinks"))
    ]
    monkeypatch.setattr("app.main.items_near", lambda *args: items)
    monkeypatch.setattr(ws.Session, "now", lambda self: datetime(2026, 11, 21, 18))
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "join"})
        recv(sock, "board")
        sock.send_json({"type": "prefs", "include": [interest]})
        board = recv(sock, "board")
        assert board["group"] == group
        assert board["count"] == 1
        assert {r["group"] for r in board["rows"]} == {group}
        sock.send_json({"type": "show", "group": None})
        assert recv(sock, "board")["count"] == 4
        sock.send_json({"type": "prefs", "include": [interest], "budget": 10})
        assert recv(sock, "board")["group"] is None
        sock.send_json({"type": "prefs", "include": []})
        assert recv(sock, "board")["group"] is None
        sock.send_json({"type": "prefs", "include": ["not a suggestion", interest]})
        assert recv(sock, "board")["group"] == group


@pytest.mark.parametrize(
    "utterance",
    [
        "just somewhere to eat",
        "a quiet pint",
        "quiz night at the pub",
        "no clubs, just somewhere to eat",
    ],
)
def test_everyday_phrasing_never_empties_the_board(
    monkeypatch: pytest.MonkeyPatch, utterance: str
) -> None:
    """Mood talk around a request must not become a concrete search that matches nothing."""
    from datetime import datetime

    monkeypatch.setattr(ws.Session, "now", lambda self: datetime(2026, 11, 21, 21, 30))
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "talk_text", "text": utterance})
        chips = recv(sock, "chips")
        assert not chips.get("requested"), f"{utterance!r} parsed as {chips.get('requested')}"
        sock.send_json(
            {
                "type": "prefs",
                "include": chips["include"],
                "exclude": chips["exclude"],
                "requested": [],
                "budget": chips.get("budget", 999),
                "student": False,
                "adult": True,
                "company": 1,
            }
        )
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        board = recv(sock, "board")
        assert board["count"] > 0, f"{utterance!r} emptied the board"


def test_pizza_and_a_laugh_surfaces_both(monkeypatch: pytest.MonkeyPatch) -> None:
    """The headline mixed request: pizza places and comedy, as hero picks from both groups."""
    from datetime import datetime

    monkeypatch.setattr(ws.Session, "now", lambda self: datetime(2026, 11, 21, 21, 30))
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "talk_text", "text": "I want to go eat pizza and have a laugh"})
        chips = recv(sock, "chips")
        assert set(chips.get("requested", [])) == {"pizza", "comedy"}
        sock.send_json(
            {
                "type": "prefs",
                "include": chips["include"],
                "exclude": chips["exclude"],
                "requested": chips.get("requested", []),
                "budget": 999,
                "student": False,
                "adult": True,
                "company": 1,
            }
        )
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        board = recv(sock, "board")
        assert {r["id"] for r in board["rows"]} == {"pizza-1", "comedy-1"}
        assert {r["category"] for r in board["rows"]} == {"food", "comedy"}
        assert {r["pick"] for r in board["rows"] if r["pick"]} == {"best", "runner_up"}


def test_dance_matches_clubs_not_plain_bars(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from app.main import items_near

    now = datetime(2026, 11, 21, 21, 30)
    sample = items_near(51.51, -0.13, now)[0]
    items = [
        dict(
            sample,
            id="club",
            name="Fabric",
            group="Drinks",
            tags=["club", "nightlife"],
            interest_terms=["night_club"],
            adult_only=True,
            opens="21:00",
            closes="04:00",
        ),
        dict(
            sample,
            id="pub",
            name="The Soho Pub",
            group="Drinks",
            tags=["nightlife"],
            interest_terms=["pub"],
            adult_only=True,
            opens="18:00",
            closes="00:00",
        ),
    ]
    monkeypatch.setattr("app.main.items_near", lambda *args: items)
    monkeypatch.setattr(ws.Session, "now", lambda _: now)
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "talk_text", "text": "I want to dance tonight"})
        chips = recv(sock, "chips")
        assert chips.get("requested") == ["dancing"]
        sock.send_json(
            {
                "type": "prefs",
                "include": chips["include"],
                "exclude": chips["exclude"],
                "requested": chips["requested"],
                "budget": 999,
                "adult": True,
            }
        )
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        board = recv(sock, "board")
        assert [r["id"] for r in board["rows"]] == ["club"]


def test_honest_empty_board_when_the_feed_has_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from app.main import items_near

    now = datetime(2026, 11, 21, 21, 30)
    sample = items_near(51.51, -0.13, now)[0]
    items = [
        dict(
            sample,
            id="noodles",
            name="Noodle Bar",
            group="Food",
            tags=["food"],
            opens="12:00",
            closes="23:00",
        )
    ]
    monkeypatch.setattr("app.main.items_near", lambda *args: items)
    monkeypatch.setattr(ws.Session, "now", lambda _: now)
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "talk_text", "text": "karaoke night with the lads"})
        chips = recv(sock, "chips")
        sock.send_json(
            {
                "type": "prefs",
                "include": chips["include"],
                "exclude": chips["exclude"],
                "requested": chips.get("requested", []),
                "budget": 999,
                "adult": True,
            }
        )
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        board = recv(sock, "board")
        assert board["rows"] == [] and board["count"] == 0


def test_enriched_is_cached_until_the_file_changes(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.setattr(ws, "_enriched_cache", (-1.0, {}))
    target = tmp_path / "enriched.json"
    monkeypatch.setattr(ws, "ENRICHED", target)
    target.write_text('{"a": {"price": 5}}')
    os.utime(target, (1, 1))
    assert ws._enriched() == {"a": {"price": 5}}
    # same mtime: the cache wins even though the bytes changed
    target.write_text('{"a": {"price": 7}}')
    os.utime(target, (1, 1))
    assert ws._enriched() == {"a": {"price": 5}}
    # new mtime: re-read; broken content means no extras
    target.write_text('{"a": {"price": 6}}')
    os.utime(target, (2, 2))
    assert ws._enriched() == {"a": {"price": 6}}
    target.write_text("not json")
    os.utime(target, (3, 3))
    assert ws._enriched() == {}


def test_location_message_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """location re-boards with the new area; out-of-range or wrong-typed values are ignored."""
    from datetime import datetime

    monkeypatch.setattr(ws.Session, "now", lambda self: datetime(2026, 11, 21, 18))
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "location", "lat": 53.48, "lng": -2.24, "label": "Manchester"})
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        assert recv(sock, "board")["area"] == "Manchester"
        for bad in (
            {"lat": 91, "lng": 0},
            {"lat": "51", "lng": 0},
            {"lat": None, "lng": None},
            {"lat": True, "lng": 0},
        ):  # bool is an int in Python: must not pass
            sock.send_json({"type": "location", **bad})
        sock.send_json({"type": "refresh_now"})
        assert recv(sock, "note")["text"]
        assert recv(sock, "board")["area"] == "Manchester"  # bad locations never stuck


def test_malformed_messages_never_break_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """One sweep of hostile frames: the connection must stay alive and keep boarding."""
    from datetime import datetime

    monkeypatch.setattr(ws.Session, "now", lambda self: datetime(2026, 11, 21, 18))
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_text("not json at all")
        sock.send_text("[1, 2, 3]")
        sock.send_text("[" * 100_000)  # deep-nested JSON bomb: RecursionError, not a crash
        sock.send_json({"type": "board_on", "item_id": None})  # reserved message: ignored
        sock.send_bytes(b"\x00\x30" * 100)  # audio while not talking: ignored
        sock.send_json({"type": "prefs", "budget": "20", "include": "food", "company": 999})
        sock.send_json({"type": "feedback", "item_id": 42, "kind": "explode"})
        sock.send_json({"type": "feedback", "item_id": "bowl-1", "kind": "maybe"})
        sock.send_json({"type": "time_travel", "now": "not a date"})
        sock.send_json({"type": "time_travel"})
        sock.send_json({"type": "show", "group": "Narnia"})
        sock.send_json({"type": "talk_text", "text": "x" * 400})
        transcript = recv(sock, "transcript")
        assert len(transcript["text"]) == 300  # truncated, not echoed whole
        recv(sock, "chips")
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        board = recv(sock, "board")
        assert board["count"] > 0  # still alive and boarding


def test_refresh_now_reaches_every_shared_member(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from app.main import items_near

    now = datetime(2026, 11, 21, 18)
    sample = items_near(51.51, -0.13, now)[0]
    items = [
        dict(sample, id="only", name="Only Place", tags=["food"], opens="00:00", closes="00:00")
    ]
    monkeypatch.setattr("app.main.items_near", lambda *args: items)
    monkeypatch.setattr(ws.Session, "now", lambda _: now)
    rooms.rooms.clear()
    with TestClient(app) as client, client.websocket_connect("/ws") as host:
        host.send_json({"type": "room_create", "name": "Host", "prefs": {}})
        invite = recv(host, "room_joined")["invite"]
        recv(host, "board")
        with client.websocket_connect("/ws") as friend:
            friend.send_json({"type": "room_join", "invite": invite, "name": "Friend", "prefs": {}})
            recv(friend, "room_joined")
            recv(friend, "board")
            recv(host, "board")
            friend.send_json({"type": "refresh_now"})  # shared: republish to everyone, no note
            assert recv(friend, "board")["members"] == ["Host", "Friend"]
            assert recv(host, "board")["members"] == ["Host", "Friend"]


def test_solo_board_drops_known_over_budget_places(monkeypatch: pytest.MonkeyPatch) -> None:
    """A capped board hides venues whose known price exceeds the cap (price_level can't know)."""
    from datetime import datetime

    from app.main import items_near

    now = datetime(2026, 11, 21, 18)
    sample = items_near(51.51, -0.13, now)[0]
    items = [
        dict(
            sample,
            id="cheap",
            name="Cheap Eats",
            tags=["food"],
            price=8.0,
            price_level=1,
            opens="00:00",
            closes="00:00",
        ),
        dict(
            sample,
            id="pricey",
            name="Fancy Restaurant",
            tags=["food"],
            price=45.0,
            price_level=2,
            opens="00:00",
            closes="00:00",
        ),
    ]
    monkeypatch.setattr("app.main.items_near", lambda *args: items)
    monkeypatch.setattr(ws.Session, "now", lambda _: now)
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json({"type": "prefs", "budget": 20, "include": [], "exclude": []})
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        board = recv(sock, "board")
        assert [r["id"] for r in board["rows"]] == ["cheap"]


def test_student_discount_is_visible_and_ranks(monkeypatch: pytest.MonkeyPatch) -> None:
    """student=true must surface the student deal on the row and in the top-3 reasons."""
    from datetime import datetime

    from app.main import load_samples

    items = [dict(i, walk_mins=8) for i in load_samples()]  # bowl-1 has student_price: true
    monkeypatch.setattr("app.main.items_near", lambda *args: [dict(i) for i in items])
    monkeypatch.setattr(ws.Session, "now", lambda self: datetime(2026, 11, 21, 18))
    with TestClient(app).websocket_connect("/ws") as sock:
        sock.send_json(
            {
                "type": "prefs",
                "budget": 999,
                "student": True,
                "adult": True,
                "include": [],
                "exclude": [],
            }
        )
        sock.send_json({"type": "join"})
        recv(sock, "joined")
        board = recv(sock, "board")
        bowl = next(r for r in board["rows"] if r["id"] == "bowl-1")
        assert bowl["student_deal"] is True
        assert any(r["text"] == "Student price" for r in bowl["reasons"])
        plain = next(r for r in board["rows"] if r["id"] == "comedy-1")
        assert plain["student_deal"] is False
        assert bowl["score"] > plain["score"]
