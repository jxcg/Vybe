import asyncio
import base64
from pathlib import Path
from typing import Any

import pytest

from pipeline import voiceover


def test_fallback_script_names_the_venue_without_assuming_it_is_open() -> None:
    item = {"id": "x", "name": "Noodle Bar", "walk_mins": 6}
    assert voiceover.fallback_script(item, {"deal": "2-for-1 bowls until 9pm"}) == (
        "2-for-1 bowls until 9pm! Noodle Bar, 6 minutes away."
    )
    s = voiceover.fallback_script(item, {})
    assert s == "Tonight's pick is Noodle Bar."
    assert (
        len(
            voiceover.fallback_script(
                {"name": "A Very Long Venue Name Indeed", "walk_mins": 3}, {}
            ).split()
        )
        < 15
    )


def test_tts_mp3_decodes_audio_data(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSpeech:
        async def complete_async(self, **kwargs: Any) -> Any:
            assert kwargs["model"] == voiceover.TTS_MODEL
            assert kwargs["voice_id"] == voiceover.VOICE
            assert kwargs["response_format"] == "mp3"

            class R:
                audio_data = base64.b64encode(b"ID3fake-mp3").decode()

            return R()

    class FakeAudio:
        speech = FakeSpeech()

    class FakeClient:
        audio = FakeAudio()

    monkeypatch.setattr(voiceover, "_client", FakeClient())
    assert asyncio.run(voiceover.tts_mp3("hello")) == b"ID3fake-mp3"


def test_make_voiceovers_writes_mp3_and_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def fake_tts(text: str) -> bytes:
        return b"ID3" + text.encode()[:20]

    monkeypatch.setattr(voiceover, "tts_mp3", fake_tts)
    items: list[dict[str, Any]] = [
        {"id": "a", "name": "A", "walk_mins": 2},
        {"id": "b", "name": "B"},
    ]
    enriched = {"a": {"script": "Two-for-one until nine."}}
    mapping = asyncio.run(voiceover.make_voiceovers(items, enriched, tmp_path))
    assert mapping == {"a": "data/voiceovers/a.mp3", "b": "data/voiceovers/b.mp3"}
    assert (tmp_path / "a.mp3").read_bytes().startswith(b"ID3Two-for-one")
    assert (tmp_path / "b.mp3").read_bytes().startswith(b"ID3Tonight")


def test_make_voiceovers_survives_one_tts_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def flaky(text: str) -> bytes:
        if "bad" in text:
            raise RuntimeError("tts down")
        return b"ID3ok"

    monkeypatch.setattr(voiceover, "tts_mp3", flaky)
    items: list[dict[str, Any]] = [{"id": "good", "name": "Good"}, {"id": "bad", "name": "bad"}]
    mapping = asyncio.run(voiceover.make_voiceovers(items, {}, tmp_path))
    assert mapping == {"good": "data/voiceovers/good.mp3"}


def test_merge_voiceovers_sets_voiceover_key() -> None:
    existing = {"a": {"deal": "2-for-1", "verified": True}, "event-x": {"new_item": {}}}
    out = voiceover.merge_voiceovers(existing, {"a": "data/voiceovers/a.mp3"})
    assert out["a"]["voiceover"] == "data/voiceovers/a.mp3"
    assert out["a"]["deal"] == "2-for-1"  # extras preserved
    assert out["event-x"] == {"new_item": {}}


def test_voiceover_workflow_registered() -> None:
    from mistralai.workflows import get_workflow_definition

    from pipeline import voiceover_wf

    assert get_workflow_definition(voiceover_wf.VybeVoiceover).name == "vybe-voiceover"
