import json
from typing import Any

import httpx
import pytest

from app import voice


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def tool_payload(filters: Any) -> dict[str, Any]:
    """A chat-completions response whose tool call carries `filters` as arguments."""
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "set_filters", "arguments": json.dumps(filters)}}
                    ]
                }
            }
        ]
    }


@pytest.fixture(autouse=True)
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)


def test_audio_to_filters_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        seen.update(kwargs)
        seen["url"] = url
        return FakeResponse(
            tool_payload(
                {
                    "budget": 1,
                    "max_walk_mins": 10,
                    "exclude_tags": ["nightlife"],
                    "reply": "Cheap, no clubs, within 10 minutes.",
                }
            )
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    context = {"current_card": {"id": "bowl-1", "tags": ["active"]}, "now": "19:05", "filters": {}}
    out = voice.audio_to_filters(b"fake-audio", "audio/webm", context)
    assert out == {
        "budget": 1,
        "max_walk_mins": 10,
        "exclude_tags": ["nightlife"],
        "reply": "Cheap, no clubs, within 10 minutes.",
    }
    body = seen["json"]
    assert seen["url"] == voice.API
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert body["model"] == voice.MODEL
    assert body["tool_choice"] == "any"
    assert body["tools"][0]["function"]["name"] == "set_filters"
    content = body["messages"][1]["content"]
    assert content[0]["type"] == "text" and "bowl-1" in content[0]["text"]
    assert content[1]["type"] == "input_audio"
    assert content[1]["input_audio"]["format"] == "webm"


def test_cleans_and_clamps_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kw: FakeResponse(
            tool_payload(
                {
                    "budget": 9,  # clamped to 3
                    "max_walk_mins": 500,  # clamped to 60
                    "type": "spaceship",  # dropped
                    "include_tags": ["active", "loud"],  # unknown tag dropped
                    "include_text": ["Bowling", "  "],  # normalised, empties dropped
                    "indoors_only": "yes",  # not a bool: dropped
                    "clear": False,
                    "unknown_key": 1,  # dropped
                    "reply": "  ok  ",
                }
            )
        ),
    )
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    out = voice.audio_to_filters(b"x", "audio/wav", {})
    assert out == {
        "budget": 3,
        "max_walk_mins": 60,
        "include_tags": ["active"],
        "include_text": ["bowling"],
        "clear": False,
        "reply": "ok",
    }


def test_http_error_returns_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, **kwargs: Any) -> FakeResponse:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", boom)
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    assert voice.audio_to_filters(b"x", "audio/mp3", {}) == {
        "reply": "Sorry, I didn't catch that — try again."
    }


def test_bad_arguments_json_returns_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"choices": [{"message": {"tool_calls": [{"function": {"arguments": "not json"}}]}}]}
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResponse(payload))
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    assert voice.audio_to_filters(b"x", "audio/webm", {}) == {
        "reply": "Sorry, I didn't catch that — try again."
    }


def test_no_key_short_circuits_without_http(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse({})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = voice.audio_to_filters(b"x", "audio/webm", {})
    assert "reply" in out
    assert not called
