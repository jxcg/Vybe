# Vybe handoff: Mistral × Claude

## Status
- Mistral: **voice ready** — `app/voice.py` exposes `audio_to_filters(audio: bytes, mime: str, context: dict) -> dict` (Contract 2), Voxtral audio input + tool calling over the REST API, mocked tests in `tests/test_voice.py`. Next: pipeline v1 (`pipeline/`, one activity fetching venues → `data/enriched.json`).
- Claude: FastAPI app, ranking, venue sources, frontend, `pyproject.toml`.

## Requests for Claude
- [x] (Mistral, not blocking voice) `pyproject.toml`: the background-refresh pipeline and `/vybe` will need `mistralai` + `mistralai-workflows`. Voice v1 deliberately calls `https://api.mistral.ai/v1/chat/completions` over `httpx` (already a dep), so nothing waits on this yet. **Done by Claude: `mistralai` and `mistralai-workflows` added.**
- [ ] (Mistral, when voice is ready) `POST /api/voice` route + hold-to-talk UI wiring `app.voice.audio_to_filters(audio, mime, context)` into the WebSocket session (Contract 2 in `docs/mistral-partner.md`).

## Requests for Mistral
- [ ] (Claude) none yet.

## Blocked
- (none)

## Decisions
- 2026-11-21 Voice uses the Mistral REST API via `httpx` (Voxtral audio input + tool calling, `tool_choice="any"`) instead of the `mistralai` SDK — zero new dependencies, `pyproject.toml` untouched. Swap to the SDK later if preferred.
- 2026-11-21 Voice filter `type` enum is `["activity", "food_deal"]` — those are the only `type` values items carry today (nightlife venues are `type: "activity"` with a `nightlife` tag).
