from datetime import datetime
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from test_ws import recv

from app import geo, rooms, ws
from app.main import app, load_samples


def test_shared_board_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    base = load_samples()[0]
    items = [
        dict(
            base,
            id=item_id,
            name=item_id,
            tags=tags,
            price=price,
            adult_only=adult,
            walk_mins=5,
            opens="00:00",
            closes="00:00",
        )
        for item_id, tags, price, adult in [
            ("Comedy", ["comedy"], 10, False),
            ("Park", ["outdoors", "culture"], None, False),
            ("Dinner", ["food"], 21, False),
            ("Club", ["club"], 5, True),
        ]
    ]
    monkeypatch.setattr(geo, "weather", lambda *_: None)
    monkeypatch.setattr(ws, "_enriched", lambda: {"Dinner": {"price": None}})
    monkeypatch.setattr("app.main.items_near", lambda *_: items)
    monkeypatch.setattr(ws.Session, "now", lambda _: datetime(2026, 11, 21, 18))

    friend_key = "3a" * 32
    with TestClient(app) as client, client.websocket_connect("/ws") as host:
        host.send_json({"type": "prefs", "include": ["food"]})
        host.send_json({"type": "join", "liked": ["Dinner"]})
        recv(host, "board")
        host.send_json({"type": "room_create", "name": "Host", "prefs": {"include": ["a laugh"]}})
        host.send_json({"type": "join"})
        owner = host.receive_json()
        assert owner["type"] == "room_joined"
        invite = owner["invite"]
        assert invite != owner["credential"]
        recv(host, "board")

        with client.websocket_connect("/ws") as friend:
            friend.send_json({"type": "room_check", "invite": "invalid"})
            assert recv(friend, "room_error")["message"]
            friend.send_json({"type": "room_check", "invite": invite})
            recv(friend, "room_ready")
            friend.send_json(
                {
                    "type": "room_join",
                    "invite": invite,
                    "name": "Friend",
                    "credential": friend_key,
                    "prefs": {"adult": False, "budget": 10, "include": ["a laugh"]},
                }
            )
            member = recv(friend, "room_joined")
            assert member["credential"] == friend_key
            assert member["credential"] not in (invite, owner["credential"])
            board = recv(host, "board")
            assert board == recv(friend, "board")
            assert board["members"] == ["Host", "Friend"]
            assert [row["id"] for row in board["rows"]] == ["Comedy", "Park"]
            assert board["rows"][1]["price_unknown"]
            assert any(
                "both picked comedy" in reason["text"].lower()
                for reason in board["rows"][0]["reasons"]
            )

            friend.send_json({"type": "talk_text", "text": "nothing outdoors"})
            assert recv(friend, "transcript")["text"] == "nothing outdoors"
            assert recv(friend, "chips")["exclude"] == ["outdoors"]

            friend.send_json(
                {
                    "type": "room_prefs",
                    "prefs": {"adult": False, "budget": 10, "exclude": ["outdoors"]},
                }
            )
            board = host.receive_json()
            assert board["type"] == "board"  # the transcript and chips stayed with the speaker
            assert board == recv(friend, "board")
            assert [row["id"] for row in board["rows"]] == ["Comedy"]
            assert "prefs" not in board and "likes" not in board

            friend.send_json({"type": "feedback", "kind": "like", "item_id": "Comedy"})
            liked = recv(host, "board")
            assert liked == recv(friend, "board")
            assert liked["rows"][0]["score"] > board["rows"][0]["score"]
            friend.send_json({"type": "feedback", "kind": "unlike", "item_id": "Comedy"})
            unliked = recv(host, "board")
            assert unliked == recv(friend, "board")
            assert unliked["rows"][0]["score"] == board["rows"][0]["score"]

        # A retry after a lost join response must attach to the same member.
        with client.websocket_connect("/ws") as friend:
            friend.send_json({"type": "room_join", "invite": invite, "credential": friend_key})
            assert recv(friend, "room_joined")["prefs"]["exclude"] == ["outdoors"]
            board = recv(friend, "board")
            assert board == recv(host, "board")
            assert board["members"] == ["Host", "Friend"]

        with client.websocket_connect("/ws") as friend:
            friend.send_json({"type": "room_resume", "invite": invite, "credential": invite})
            recv(friend, "room_error")
            friend.send_json(
                {"type": "room_resume", "invite": invite, "credential": member["credential"]}
            )
            assert recv(friend, "room_joined")["liked"] == []
            board = recv(friend, "board")
            assert board == recv(host, "board")
            assert board["members"] == ["Host", "Friend"]
            assert [row["id"] for row in board["rows"]] == ["Comedy"]
            friend.send_json({"type": "room_leave"})
            recv(friend, "room_left")
            assert recv(friend, "board")["members"] == ["You"]
            assert recv(host, "board")["members"] == ["Host"]
            friend.send_json(
                {"type": "room_resume", "invite": invite, "credential": member["credential"]}
            )
            recv(friend, "room_error")

            friend.send_json({"type": "room_create", "name": "Different room", "prefs": {}})
            other = recv(friend, "room_joined")
            assert other["invite"] != invite
            assert recv(friend, "board")["members"] == ["Different room"]
            host.send_json({"type": "room_prefs", "prefs": {"exclude": ["outdoors"]}})
            assert recv(host, "board")["members"] == ["Host"]
            friend.send_json({"type": "room_prefs", "prefs": {"exclude": ["comedy"]}})
            isolated = recv(friend, "board")
            assert isolated["members"] == ["Different room"]
            assert "Park" in {row["id"] for row in isolated["rows"]}
            rooms.rooms[other["invite"]].expires = monotonic() - 1
            friend.send_json({"type": "room_check", "invite": other["invite"]})
            assert "expired" in recv(friend, "room_error")["message"]

        host.send_json({"type": "room_leave"})
        recv(host, "room_left")
        solo = recv(host, "board")
        assert {row["id"] for row in solo["rows"]} == {"Dinner"}


def test_group_ranking_prefers_the_worst_off_member_then_the_average() -> None:
    base = dict(
        load_samples()[0], price=None, adult_only=False, walk_mins=5, opens="00:00", closes="00:00"
    )
    items = [
        dict(base, id="polar", tags=["comedy"]),
        dict(base, id="balanced", tags=["comedy", "music"]),
        dict(base, id="stronger", tags=["comedy", "active"]),
    ]
    members = [
        rooms.Member("Host", rooms.preferences({"include": ["a laugh", "active"]}), set(), None),
        rooms.Member(
            "Friend", rooms.preferences({"include": ["live music", "active"]}), set(), None
        ),
    ]
    results = rooms.group_rank(items, datetime(2026, 11, 21, 18), None, members)
    assert [row["id"] for row in results] == ["stronger", "balanced", "polar"]
    assert results[0]["match"] == results[1]["match"] > results[2]["match"]
    assert results[0]["average"] > results[1]["average"]
