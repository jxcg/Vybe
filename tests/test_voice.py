import json
import time
from typing import Any

import httpx
import pytest

from app import voice


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            request = httpx.Request("POST", voice.API)
            raise httpx.HTTPStatusError(
                f"{self._status}",
                request=request,
                response=httpx.Response(self._status, request=request),
            )

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
    out = voice.audio_to_filters(b"fake-audio", "audio/webm;codecs=opus", context)
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
    # codecs=opus is stripped from the MIME type
    assert content[1]["input_audio"]["format"] == "webm"


def test_cleans_clamps_and_fills_reply(monkeypatch: pytest.MonkeyPatch) -> None:
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
                    # no reply: a fallback is filled in
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
        "reply": "Filters updated for this session.",
    }


def test_http_4xx_raises_voice_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResponse({}, status=400))
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(voice.VoiceError):
        voice.audio_to_filters(b"x", "audio/webm", {})


def test_network_error_raises_voice_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, **kwargs: Any) -> FakeResponse:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", boom)
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(voice.VoiceError):
        voice.audio_to_filters(b"x", "audio/mp3", {})


def test_no_tool_call_raises_voice_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: FakeResponse({"choices": [{"message": {}}]})
    )
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(voice.VoiceError):
        voice.audio_to_filters(b"x", "audio/webm", {})


def test_bad_arguments_json_raises_voice_error(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"choices": [{"message": {"tool_calls": [{"function": {"arguments": "not json"}}]}}]}
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResponse(payload))
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(voice.VoiceError):
        voice.audio_to_filters(b"x", "audio/webm", {})


def test_timeout_raises_voice_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(url: str, **kwargs: Any) -> FakeResponse:
        time.sleep(1.0)
        return FakeResponse(tool_payload({"reply": "too late"}))

    monkeypatch.setattr(httpx, "post", slow)
    monkeypatch.setattr(voice, "DEADLINE", 0.2)  # one total deadline, not per-stage
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(voice.VoiceError, match="timed out"):
        voice.audio_to_filters(b"x", "audio/webm", {})


def test_apply_filters_is_pure_and_ephemeral() -> None:
    items = [
        {
            "id": "a",
            "name": "Bowling Alley",
            "type": "activity",
            "price_level": 2,
            "walk_mins": 5,
            "tags": ["active", "indoors"],
        },
        {
            "id": "b",
            "name": "Night Club",
            "type": "activity",
            "price_level": 3,
            "walk_mins": 20,
            "tags": ["nightlife", "indoors"],
        },
        {
            "id": "c",
            "name": "Hyde Park",
            "type": "activity",
            "price_level": 1,
            "walk_mins": 15,
            "tags": ["active", "outdoors"],
        },
    ]
    # empty session filters: feed unchanged
    assert voice.apply_filters(items, {}) == items
    assert voice.apply_filters(items, {"budget": 1}) == [items[2]]
    assert [i["id"] for i in voice.apply_filters(items, {"max_walk_mins": 10})] == ["a"]
    assert [i["id"] for i in voice.apply_filters(items, {"exclude_tags": ["nightlife"]})] == [
        "a",
        "c",
    ]
    assert [i["id"] for i in voice.apply_filters(items, {"include_tags": ["outdoors"]})] == ["c"]
    assert [i["id"] for i in voice.apply_filters(items, {"include_text": ["bowling"]})] == ["a"]
    assert [i["id"] for i in voice.apply_filters(items, {"exclude_text": ["club", "park"]})] == [
        "a"
    ]
    assert [i["id"] for i in voice.apply_filters(items, {"indoors_only": True})] == ["a", "b"]
    assert [i["id"] for i in voice.apply_filters(items, {"budget": 2, "max_walk_mins": 10})] == [
        "a"
    ]
    # the input list is not mutated
    assert [i["id"] for i in items] == ["a", "b", "c"]


def test_no_key_raises_without_http(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse({})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(voice.VoiceError):
        voice.audio_to_filters(b"x", "audio/webm", {})
    assert not called
