"""Voxtral TTS voiceovers for cards (Contract 3): one short mp3 per venue.

Scripts come from the Enricher (`script` in data/enriched.json); when there is
none yet, a code template fills in from the item. Generated only in the
background pipeline — never live — into data/voiceovers/<id>.mp3, referenced
from enriched.json as `voiceover` (which app/ws.py already maps to
`voiceover_url`).
"""

import asyncio
import base64
import os
from pathlib import Path
from typing import Any

from mistralai.client import Mistral

TTS_MODEL = "voxtral-mini-tts-3"  # voxtral-mini-tts-latest / -2603 also exist
VOICE = "en_paul_happy"  # one consistent, upbeat voice (preset slug)
MAX_VOICEOVERS = 20  # per run, keeps cost down

_client: Mistral | None = None


def _mistral() -> Mistral:
    global _client
    if _client is None:
        _client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY"))
    return _client


async def tts_mp3(text: str) -> bytes:
    """Voxtral TTS: script text → mp3 bytes."""
    r = await _mistral().audio.speech.complete_async(
        input=text, model=TTS_MODEL, voice_id=VOICE, response_format="mp3"
    )
    return base64.b64decode(r.audio_data)


def fallback_script(item: dict[str, Any], extra: dict[str, Any]) -> str:
    """Code template for the voiceover when the Enricher hasn't written one (<15 words)."""
    name = str(item.get("name", "This spot"))
    deal = extra.get("deal")
    walk = item.get("walk_mins")
    if deal:
        return f"{deal}! {name}" + (f", {walk} minutes away." if walk else ".")
    return f"{name} is open now" + (f" — {walk} minutes away." if walk else ".")


def _voiceovers_dir() -> Path:
    # lazy: module-level Path.resolve() is rejected inside Temporal's sandbox
    return Path(__file__).resolve().parent.parent / "data" / "voiceovers"


async def make_voiceovers(
    items: list[dict[str, Any]], enriched: dict[str, Any], out_dir: Path | None = None
) -> dict[str, str]:
    """Generate one mp3 per item (cap MAX_VOICEOVERS); returns {id: relative path}."""
    out_dir = out_dir or _voiceovers_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}

    async def one(item: dict[str, Any]) -> tuple[str, str] | None:
        iid = item["id"]
        extra = enriched.get(iid) or {}
        script = extra.get("script") or fallback_script(item, extra)
        try:
            mp3 = await tts_mp3(script)
        except Exception:
            return None  # one bad card must not fail the run
        rel = f"data/voiceovers/{iid}.mp3"
        (out_dir / f"{iid}.mp3").write_bytes(mp3)
        return iid, rel

    for res in await asyncio.gather(*[one(i) for i in items[:MAX_VOICEOVERS]]):
        if res:
            mapping[res[0]] = res[1]
    return mapping


def merge_voiceovers(existing: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Set the `voiceover` key per venue in the enriched mapping (read-modify-write)."""
    out = dict(existing)
    for iid, rel in mapping.items():
        entry = dict(out.get(iid, {}))
        entry["voiceover"] = rel
        out[iid] = entry
    return out
