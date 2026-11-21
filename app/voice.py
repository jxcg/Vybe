"""Voxtral voice → session filters (Contract 2 in docs/mistral-partner.md).

No web framework code here, and nothing is ever persisted: the spoken request
goes to Voxtral as audio with tool calling, and only the parsed filters come back.
Calls the Mistral REST API over httpx so no new dependency is needed.

Any failure (missing key, network/HTTP error, timeout, unparseable reply) raises
VoiceError, so the route can answer 502 instead of pretending the user was heard.
"""

import base64
import concurrent.futures
import json
import os
from typing import Any

import httpx

API = "https://api.mistral.ai/v1/chat/completions"
# voxtral-mini-* 400s on audio input (checked live 2026-11-21); the dated small ID
# is the stable one — voxtral-small-latest is its alias
MODEL = "voxtral-small-2507"
DEADLINE = 1.9  # one total deadline for the whole call: this runs live
_TRANSPORT = httpx.Timeout(1.8, connect=0.5)  # per-stage backstop under DEADLINE


class VoiceError(RuntimeError):
    """Voice request failed: bad config, network/HTTP error, timeout, bad reply."""


TAGS = ["active", "culture", "nightlife", "food", "indoors", "outdoors"]
TYPES = ["activity", "food_deal"]

FILTER_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "set_filters",
        "description": "Session filters from the spoken request. Omit anything not said.",
        "parameters": {
            "type": "object",
            "properties": {
                "budget": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                    "description": "Max price level: 1 = cheap, 2 = mid, 3 = anything.",
                },
                "max_walk_mins": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 60,
                    "description": "Only places within this many minutes' walk.",
                },
                "type": {"type": "string", "enum": TYPES},
                "include_tags": {"type": "array", "items": {"type": "string", "enum": TAGS}},
                "exclude_tags": {"type": "array", "items": {"type": "string", "enum": TAGS}},
                "include_text": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Name fragments that must appear, e.g. ['bowling'].",
                },
                "exclude_text": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Name fragments to avoid, e.g. ['club'].",
                },
                "indoors_only": {"type": "boolean"},
                "clear": {
                    "type": "boolean",
                    "description": "True only when the user asks to reset their filters.",
                },
                "reply": {"type": "string", "description": "One short sentence for the UI."},
            },
            "required": ["reply"],
            "additionalProperties": False,
        },
    },
}

SYSTEM = (
    "You are Vybe's voice control. The user holds a button and says a short request about "
    "what to do near them right now. Turn only what they said into session filters with the "
    "set_filters tool; omit anything they did not say. Use the context (current card, current "
    'time, current filters) for relative requests like "like this but closer" or "not this '
    'kind of thing". Set clear=true only when they ask to reset. reply is one short, upbeat '
    "sentence for the UI, in the language they spoke."
)


def _clean(raw: Any) -> dict[str, Any]:
    """Keep only the contract keys, clamped to valid values."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    budget = raw.get("budget")
    if isinstance(budget, int) and not isinstance(budget, bool):
        out["budget"] = min(3, max(1, budget))
    walk = raw.get("max_walk_mins")
    if isinstance(walk, int) and not isinstance(walk, bool):
        out["max_walk_mins"] = min(60, max(1, walk))
    if raw.get("type") in TYPES:
        out["type"] = raw["type"]
    for key in ("include_tags", "exclude_tags"):
        tags = raw.get(key)
        if isinstance(tags, list):
            kept = [t for t in tags if t in TAGS]
            if kept:
                out[key] = kept
    for key in ("include_text", "exclude_text"):
        words = raw.get(key)
        if isinstance(words, list):
            kept = [w for w in (str(x).strip().lower() for x in words) if w]
            if kept:
                out[key] = kept
    for key in ("indoors_only", "clear"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    reply = raw.get("reply")
    if isinstance(reply, str) and reply.strip():
        out["reply"] = reply.strip()
    return out


def _post(payload: dict[str, Any], key: str) -> httpx.Response:
    return httpx.post(
        API, json=payload, headers={"Authorization": f"Bearer {key}"}, timeout=_TRANSPORT
    )


def audio_to_filters(audio: bytes, mime: str, context: dict[str, Any]) -> dict[str, Any]:
    """Voxtral: a spoken request turned into session filters.

    `context` is what the user is looking at, e.g. {"current_card": {...item...},
    "now": "19:05", "filters": {...current filters...}}, so relative requests like
    "like this but closer" work. Returns only the Contract 2 shape; every key is
    optional. Never writes anything to disk, database or logs. Raises VoiceError
    on any failure.
    """
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise VoiceError("MISTRAL_API_KEY is not set")
    fmt = mime.split("/")[-1].split(";")[0].strip() or "webm"  # "audio/webm;codecs=opus" -> "webm"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Context (what the user is looking at): "
                        + json.dumps(context, ensure_ascii=False),
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": base64.b64encode(audio).decode(), "format": fmt},
                    },
                ],
            },
        ],
        "tools": [FILTER_TOOL],
        "tool_choice": "any",
    }
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_post, payload, key)
        try:
            r = future.result(timeout=DEADLINE)  # one total deadline, not per-stage
        except concurrent.futures.TimeoutError as e:
            raise VoiceError("voice request timed out") from e
        except Exception as e:  # network errors surface here from the worker thread
            raise VoiceError(f"voice request failed: {e}") from e
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    try:
        r.raise_for_status()
        calls = r.json()["choices"][0]["message"].get("tool_calls") or []
        if not calls:
            raise VoiceError("Voxtral returned no tool call")
        args = json.loads(calls[0]["function"]["arguments"])
    except VoiceError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
        raise VoiceError(f"could not parse Voxtral reply: {e}") from e
    out = _clean(args)
    out.setdefault("reply", "Filters updated for this session.")
    return out
