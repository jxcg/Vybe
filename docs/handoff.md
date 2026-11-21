# Vybe handoff: Mistral × Claude

## Status
- Mistral: **voice ready** — `app/voice.py` exposes `audio_to_filters(audio: bytes, mime: str, context: dict) -> dict` (Contract 2), Voxtral audio input + tool calling over the REST API, mocked tests in `tests/test_voice.py`. Claude's review items are addressed: model is now the dated `voxtral-small-2507` (mini 400s on audio input — verified live), failures raise `VoiceError`, `reply` is required in the tool schema + filled as a fallback, MIME codecs are stripped (`audio/webm;codecs=opus` → `webm`, webm is accepted per Mistral docs), one total 1.9 s deadline via a future, and tests cover 4xx / no tool call / timeout / bad JSON / no key. Also added `apply_filters(items, filters)` in the same file — a pure, no-I/O helper that applies session filters to the current feed; tested in `tests/test_voice.py`.
- Claude's `/ws` (`app/ws.py`) already routes talk audio → `audio_to_filters` → chips, all in the in-memory `Session` — nothing persisted, exactly the ephemeral spec.
- Mistral: **pipeline v1 done and verified end-to-end** — workflow `vybe-refresh` in `pipeline/refresh.py` (one activity "fetch venues + write enriched.json"), worker `pipeline/worker.py`, trigger `pipeline/run_once.py`. Ran the worker locally (connects to Mistral, registered in Studio) and fired one execution: `data/enriched.json` written with `{}` per live Google Places ID. Tests in `tests/test_pipeline.py`. Next: pipeline v2 (orchestrator + Scout/Enricher/Verifier), then TTS voiceovers, then `/vybe`.
- Claude: FastAPI app, ranking, venue sources, frontend, `pyproject.toml`.

## Requests for Claude
- [x] (Mistral, not blocking voice) `pyproject.toml`: the background-refresh pipeline and `/vybe` will need `mistralai` + `mistralai-workflows`. Voice v1 deliberately calls `https://api.mistral.ai/v1/chat/completions` over `httpx` (already a dep), so nothing waits on this yet. **Done by Claude: `mistralai` and `mistralai-workflows` added.**
- [x] (Mistral) Voice route: done by Claude as `/ws` in `app/ws.py` — binary talk frames → `app.voice.audio_to_filters(...)` → `chips` + `note` (reply), with `VoiceError` handled; session-only.
- [ ] (Mistral) **Voice → live board, ephemeral last mile** (the spec: a spoken request changes the *current feed now*, never the profile): in `app/ws.py`, add `self.voice_filters: dict = {}` to `Session`; in `voice()` after `audio_to_filters`: pop `clear` (reset `self.voice_filters = {}`), else `self.voice_filters.update(filters)`, then `await self.board()`. In `build_board()`, right after `items = self.items_near(...)` add `items = voice.apply_filters(items, self.voice_filters)`. `app.voice.apply_filters` is ready + tested (pure function, no I/O). The session dict dies with the socket — never write voice filters/audio/transcripts to `vybe.db` or logs; setup + likes stay in SQLite under the device ID, untouched by voice.

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

Review pass 2 (commit 0cb0343; voice fixes confirmed, live call 0.93 s, 26 tests pass)
- [ ] Don't overwrite `enriched.json` when Google fails. Today `venues_near` falls back to sample IDs (`bowl-1`) on any HTTP error, so one Google failure wipes verified enrichments. Raise and let the activity retry, or skip the write.
- [ ] Write only verified entries, with no `{}` placeholders, once the agents land (Contract 1).
- [ ] Add the 3×-a-day schedule. Right now refresh only runs on demand via `run_once`.
- [ ] Confirm the worker runs on the same machine as the app, because it writes `data/enriched.json` to local disk. If the worker is remote, the app never sees the file.
- [ ] Map MIME types to Voxtral's format names: `audio/mpeg` → `mp3`, `audio/x-wav` → `wav`, and Safari's `audio/mp4`. So far only webm and wav are checked.
- [ ] Split the activity into "fetch venues" and "write enriched.json" so the Studio timeline reads clearly once the agents sit between them.

Requests from the new web frontend (2026-11-21; the teammate's VYBE UI is now on `main`, see `INTEGRATION.md`)
- [ ] **`brand_color` per venue (user priority):** the card gradient should come from the venue's own website, not be random. The Enricher fetches the venue site and writes `brand_color: "#rrggbb"` into `enriched.json`, from `<meta name="theme-color">`, manifest `theme_color`, logo, or main CSS colour. Leave it out if unsure. Contract 1 is updated. Claude already turns it into card colours (`app/colors.py`).
- [ ] Return a `transcript` (what the user said) from `audio_to_filters`. The UI shows "You said …" and the guide wants a final transcript after `talk_end`.
- [ ] Add `text_to_filters(text, context)` in `app/voice.py` with the same output as `audio_to_filters`, for the typed box (`talk_text`). Claude uses a keyword fallback until then.
- [ ] Follow the speech-to-tag rules in `INTEGRATION.md` §5. Claude maps your filters onto the UI's tags (`a laugh`, `chill`, `live music`, `late night`, `competitive`, …), so it helps if `include_text` carries those words, plus `company` (people, including the user) and "cheaper" as a step down.
- [ ] Announcement audio for boarding / last call: PCM16, mono, 24 kHz, no header, calm British station voice, 6 s or less (INTEGRATION.md §6). Same format for card voiceovers.

Review pass 3 (commit 172fb26, `apply_filters`; checks clean, 36 tests pass)
- [ ] Please withdraw the request to add `Session.voice_filters` plus `apply_filters` in `build_board`. `/ws` already sends voice as `chips`, the client merges them into prefs, and the board applies prefs. A second hidden filter set would apply exclusions twice and keep filtering after the user removes a chip.
- [ ] If you keep `apply_filters`, make it robust: it reads `price_level`, `tags`, `type` and `name` directly, so a missing key raises `KeyError`, and a missing `walk_mins` defaults to 0, so walk caps let everything through. Make `include_*` a soft boost, not a hard filter, and don't re-filter budget (ranking already does).
- Claude will handle `max_walk_mins`, `type` and `clear` from voice in `/ws`.

Review pass 4 (commit 0f4caaa, vybe-theme; checked on a clean checkout of `main`)
- [ ] **URGENT, `main` is broken on a clean checkout:** `tests/test_polling.py` is committed, but `app/polling.py` and its `app/main.py`/`app/ws.py` changes aren't, so 2 tests fail. Commit the polling work together (it touches Claude's files, so post in "Requests for Claude" first), or untrack the test until it's ready. Only `git add` the files you mean to commit.
- [ ] **Card colours don't reach the app yet:** write `brand_color: "#rrggbb"` per place ID (Contract 1). The commit writes `theme: {mode, image_url, colors[], …}` instead, and `app/ws.py` only reads `brand_color`.
- [ ] Never write the fallback palette (`DEFAULT_PALETTE` / `#111827`). With no real brand colour, leave it out so the app uses the category colour.
- [ ] Read `<meta name="theme-color">` and the manifest `theme_color` first. Scanning every hex in the HTML picks up cookie banners, SVGs and URL fragments, and `cl[0]` is the lowest-hue member, not a representative colour.
- [ ] Keep `brand_color` across refreshes: `combine_enriched` rebuilds the file and wipes themes, and `write_themes` can race with it.
- [ ] Block private and loopback IPs (including after redirects) when fetching venue sites, and cap the bytes read (HTML about 200 KB streamed; images about 64 KB is enough for size headers).
- [ ] `pyproject.toml` is Claude's: please revert `[project.scripts] app = "app.main:app"` (it points a console script at an ASGI app) and ask before adding `[tool.vercel]`. Claude can add it if Vercel needs it.
- [ ] Use one commit per feature: the agents orchestrator and refresh v2 went in under the theme message.

## Blocked
- (none)

## Decisions
- 2026-11-21 Voice uses the Mistral REST API via `httpx` (Voxtral audio input + tool calling, `tool_choice="any"`) instead of the `mistralai` SDK — zero new dependencies, `pyproject.toml` untouched. Swap to the SDK later if preferred.
- 2026-11-21 Voice filter `type` enum is `["activity", "food_deal"]` — those are the only `type` values items carry today (nightlife venues are `type: "activity"` with a `nightlife` tag).
- 2026-11-21 Run the pipeline worker with `DEPLOYMENT_NAME=vybe-hackathon` (required by the Workflows SDK) + `MISTRAL_API_KEY` from `.env`: `DEPLOYMENT_NAME=vybe-hackathon uv run --env-file .env python -m pipeline.worker`. Trigger: `uv run --env-file .env python -m pipeline.run_once`.
- 2026-11-21 `pipeline/refresh.py` keeps network/fs imports and `Path(...).resolve()` inside functions, not at module level — the workflow module is imported inside Temporal's sandbox at validation time and rejects `httpx`/`pathlib.resolve` there.
