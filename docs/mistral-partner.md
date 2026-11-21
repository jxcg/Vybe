# Partner brief: Mistral (Vibe CLI) × Claude on Vybe

You are **Mistral Large**, working in the Mistral Vibe CLI on **Vybe**, a hackathon app (Mistral Vibe Hackathon 2026, London). You have a partner: **Claude** (Claude Code), working in the same repo at the same time.

Read `AGENTS.md` first. Its rules apply to you too.

---

## The product in one paragraph

Vybe shows things to do near you **right now**: full-screen cards you swipe up and down, ranked for you. Each card shows the place's **Google rating** (★ out of 5, untouched) and a **match %** (how well it suits you now: likes, walk, budget, quality, weather, time left). It also shows a time badge (🟢 plenty of time · 🟡 leave soon · 🔴 last chance), a leave-by time and 3 reasons. There's no login: setup and likes live in the browser. Users can **hold to talk** to change the board for the current session only; nothing they say is saved.

## Who does what

| Area | Owner | Notes |
| --- | --- | --- |
| Background refresh: **Mistral Workflows** + **Agents SDK** (Scout, Enricher, Verifier subagents) | **Mistral** | Your main job |
| **Voxtral**: voice → filters, and TTS voiceovers | **Mistral** | Your second job |
| The `/vybe` Vibe skill that triggers a refresh | **Mistral** | |
| FastAPI app, ranking, venue sources (Google Places), API contracts | **Claude** | |
| Frontend and design | **Claude** | |
| Wiring your outputs into the app (merge, endpoints, UI) | **Claude** | You produce data and functions; Claude plugs them in |

**Stay in your lane.** Only edit files you own. If you need a change in Claude's files, write it under "Requests for Claude" in `docs/handoff.md` instead of editing their code.

### File ownership

| Mistral owns | Claude owns |
| --- | --- |
| `pipeline/` (workflow, agents, worker) | `app/main.py`, `app/ranking.py`, `app/places.py`, `app/osm.py`, `app/geo.py` |
| `app/voice.py` (Voxtral functions only, no FastAPI routes) | `app/static/` |
| `data/enriched.json` (written by the pipeline) | `tests/test_api.py`, `tests/test_ranking.py`, `tests/test_osm.py` |
| `data/voiceovers/` (audio files) | `pyproject.toml` (ask before adding a dependency) |
| `tests/test_pipeline.py`, `tests/test_voice.py` | |

`docs/handoff.md` is shared. Append to it; don't rewrite the other side's notes.

---

## Contract 1: the pipeline output (`data/enriched.json`)

The app already gets live venues from Google Places. Your pipeline **adds to** them; it doesn't replace them. Write one JSON object keyed by item ID:

```json
{
  "ChIJxxxxxxxx": {
    "deal": "2-for-1 bowls until 9pm",
    "student_price": true,
    "price": 6.5,
    "script": "Two-for-one noodle bowls, six minutes away. Go before nine.",
    "voiceover": "data/voiceovers/ChIJxxxxxxxx.mp3",
    "verified": true,
    "verify_note": "Deal confirmed on the venue's own site",
    "checked_at": "2026-11-21T18:05:00Z",
    "source_url": "https://..."
  },
  "event-<slug>": {
    "new_item": {
      "id": "event-<slug>", "name": "...", "type": "activity",
      "price": 10.0, "price_level": 2, "student_price": false, "adult_only": false,
      "rating": null, "opens": "19:00", "closes": "23:00",
      "lat": 51.5, "lng": -0.1, "tags": ["culture", "indoors"],
      "url": "https://...", "maps_url": null, "source": "Scout agent"
    },
    "script": "...", "voiceover": "...", "verified": true, "checked_at": "..."
  }
}
```

Rules:
- **Keys** are Google Places IDs (the `id` field the app already uses) for existing venues, or `event-<slug>` for new things the Scout finds. New things carry a full `new_item` in the exact item shape above.
- **Only write `verified: true` entries.** The Verifier drops anything it can't confirm, such as fake discounts, wrong prices or ended events.
- **Tags** use only: `active`, `culture`, `nightlife`, `food`, `indoors`, `outdoors`.
- `opens` and `closes` are `HH:MM`. A close earlier than the open means after midnight.
- Write atomically: write a temp file, then rename it, so the app never reads half a file.

Claude will merge this onto live items by ID. Until then, the file just needs to be valid.

## Contract 2: voice → filters (`app/voice.py`)

Expose one function, with no web framework code:

```python
def audio_to_filters(audio: bytes, mime: str, context: dict) -> dict:
    """Voxtral: a spoken request turned into session filters."""
```

- `context` is what the user is looking at: `{"current_card": {...item...}, "now": "19:05", "filters": {...current filters...}}`. It lets relative requests work, e.g. "like this but closer" or "not this kind of thing".
- Return **only** this shape. Every key is optional; omit what wasn't said:

```json
{
  "budget": 1,
  "max_walk_mins": 10,
  "type": "activity",
  "include_tags": ["active"],
  "exclude_tags": ["nightlife"],
  "include_text": ["bowling"],
  "exclude_text": ["club"],
  "indoors_only": true,
  "clear": false,
  "reply": "Cheap, active, no clubs: 4 places within 10 minutes."
}
```

- `"clear": true` means "reset my filters".
- `reply` is one short sentence for the UI, and optionally for TTS.
- Use Voxtral's audio input with **tool calling** (`tools` plus `tool_choice="any"`), so the model fills in the filter arguments directly from the audio. If that turns out to be unreliable, fall back to transcribing first, then use a small Mistral model with the same tool.
- **Never persist anything.** No files, no database, no logs of what users said.
- Target **under 2 seconds** end to end. This runs live.

Claude will add the `POST /api/voice` route, keep filters in the session, apply them in ranking, and build the hold-to-talk UI.

## Contract 3: voiceovers

- One short script per card (under 15 words, upbeat, says *why now*), written by the Enricher.
- Voxtral TTS turns each script into `data/voiceovers/<id>.mp3`, using one consistent voice. If voice cloning is available, the team will supply a short recording.
- Generate them in the pipeline, never live.

---

## The refresh workflow (your design, suggested shape)

```
Mistral Workflow  (schedule: 3× a day, plus on-demand for "Run refresh now" and /vybe)
  └─ activity: fetch venues near a point   (call Claude's existing app.places.nearby + to_item; don't re-implement)
  └─ activity: run orchestrator agent (Agents SDK) with subagents, in parallel:
        • Scout     – tonight's events and deals near the point (web search)
        • Enricher  – deal, student price, price, voiceover script per venue
        • Verifier  – checks each claim against sources; drops anything unconfirmed
  └─ activity: Voxtral TTS for each verified script
  └─ activity: write data/enriched.json atomically
```

- Use the **Agents SDK subagents**, not "durable agents" (the docs say those are being deprecated).
- Workflows is in **public preview**; check the docs for current API names.
- The Studio timeline is part of the demo, so name activities clearly.
- Input to the workflow: `{"lat": float, "lng": float}`.
- It must be safe to re-run: same input, same file shape.

### Stretch: "Vybe Night" (only after the above works)

A per-night Workflow the user talks to:
1. The user says their plan ("3 hours, £20, active then food").
2. Agents build a 2–3 stop route.
3. Voice changes are sent in as Workflow signals, and it re-plans.
4. Timers fire "leave now" nudges.
5. It ends when the night ends, and nothing is saved.

Agree the API shape with Claude in `docs/handoff.md` before building it.

---

## Working together

- **Both of you push to `main`** (the hackathon rule in `AGENTS.md`). Before every push: `git pull --rebase`, run the checks, then push. Make small, frequent commits.
- **Checks before every commit:** `uv run ruff format . && uv run ruff check . && uv run mypy app tests && uv run pytest`. Your code must pass strict mypy. Put pipeline code under `app/`, or ask Claude to add `pipeline` to the mypy paths.
- **Commits:** conventional commits, and **no AI co-author lines or "Generated with" footers**.
- **Keys:** `.env` has `MISTRAL_API_KEY` and `GOOGLE_PLACES_API_KEY`. Run with `uv run --env-file .env ...`. Never print, log or commit keys.
- **Dependencies:** ask in `docs/handoff.md` before adding one. Claude owns `pyproject.toml`. Likely needs: `mistralai`, `mistralai-workflows`.
- **Tests:** mock all network calls (Mistral, Google). Tests must pass offline.
- **When blocked:** write it in `docs/handoff.md` under "Blocked", then work on something else. Don't wait.
- **Keep it simple:** functionality first, smallest working version, no abstractions nobody asked for. This is a hackathon.

## `docs/handoff.md` format

```markdown
## Status
- Mistral: <what you're on, what's done>
- Claude: <what Claude is on>

## Requests for Claude
- [ ] <request> (who's asking, why)

## Requests for Mistral
- [ ] <request>

## Blocked
- <thing>: <why>

## Decisions
- <date> <decision>
```

## Your first tasks, in order

1. Read `AGENTS.md`, `app/places.py`, `app/ranking.py` and this file. Create `docs/handoff.md` with your status.
2. **Voice:** build `app/voice.py`, `audio_to_filters` (Contract 2), with a mocked test. Post "voice ready" in the handoff.
3. **Pipeline v1:** a Workflow with one activity that fetches venues and writes `data/enriched.json` with an empty object per venue. Get it running locally and visible in Studio.
4. **Pipeline v2:** add the orchestrator with the Enricher and Verifier, then the Scout.
5. **Voiceovers:** add TTS to the pipeline.
6. **`/vybe` skill:** triggers the workflow via the API.

When something is done, say so in `docs/handoff.md` with the function or file name and how to call it.
