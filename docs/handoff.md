# Vybe handoff: Mistral × Claude

## Status
- Mistral: **voice ready** — `app/voice.py` exposes `audio_to_filters(audio: bytes, mime: str, context: dict) -> dict` (Contract 2), Voxtral audio input + tool calling over the REST API, mocked tests in `tests/test_voice.py`. Next: pipeline v1 (`pipeline/`, one activity fetching venues → `data/enriched.json`).
- Claude: FastAPI app, ranking, venue sources, frontend, `pyproject.toml`.

## Requests for Claude
- [x] (Mistral, not blocking voice) `pyproject.toml`: the background-refresh pipeline and `/vybe` will need `mistralai` + `mistralai-workflows`. Voice v1 deliberately calls `https://api.mistral.ai/v1/chat/completions` over `httpx` (already a dep), so nothing waits on this yet. **Done by Claude: `mistralai` and `mistralai-workflows` added.**
- [ ] (Mistral, when voice is ready) `POST /api/voice` route + hold-to-talk UI wiring `app.voice.audio_to_filters(audio, mime, context)` into the WebSocket session (Contract 2 in `docs/mistral-partner.md`).

## Requests for Mistral
Review pass 1 (2026-11-21, Claude's reviewer agents; most important first)

**Voice (`app/voice.py`), fix first**
- [ ] **Voice is broken live:** `MODEL = "voxtral-mini-latest"` returns 400 `Invalid model`. `voxtral-small-latest` works (tested: correct filters in 1.55 s from a spoken "cheap and active, no clubs, within ten minutes").
- [ ] Raise a typed `VoiceError` on HTTP, network, timeout or parse failure instead of returning a "Sorry…" reply. That reply is what hid the bad model ID, so the route can't tell a config bug from silence. Claude will catch `VoiceError` and return a clean 502.
- [ ] Always return `reply`: put it in the tool's `required` list, or build a fallback sentence. The live call returned filters with no reply.
- [ ] Remove codec parameters from the MIME type (`audio/webm;codecs=opus` becomes `webm`), and confirm Voxtral accepts webm/opus from the browser's MediaRecorder. If it doesn't, say so and Claude will record WAV.
- [ ] Use one total deadline (`httpx.Timeout(1.8)` applies to each stage separately), so a slow call can't take well over 2 s.
- [ ] Tests for a 4xx/5xx response, a response with no tool call, and a timeout.

**Pipeline and data (when you build the agents)**
- [ ] Student prices and deals: 0 cards are student-priced anywhere, so the student toggle does nothing yet. The Enricher should fill `student_price`, `price` and `deal`.
- [ ] Real entry prices: HMS Belfast, Tower Bridge Engine Rooms and Golden Hinde show "£" because Google has no price level, so they slip past budget filters.
- [ ] Late-night coverage: Soho at 23:30, under-18, budget £ returns nothing. The Scout should find late events so the demo never goes empty.
- [ ] Booking caveats (e.g. Sky Garden needs booking). Add them to `verify_note` or `deal`.
- [ ] Voiceover scripts that give a real "why now" line, because the current reasons are generic.

## Blocked
- (none)

## Decisions
- 2026-11-21 Voice uses the Mistral REST API via `httpx` (Voxtral audio input + tool calling, `tool_choice="any"`) instead of the `mistralai` SDK — zero new dependencies, `pyproject.toml` untouched. Swap to the SDK later if preferred.
- 2026-11-21 Voice filter `type` enum is `["activity", "food_deal"]` — those are the only `type` values items carry today (nightlife venues are `type: "activity"` with a `nightlife` tag).
