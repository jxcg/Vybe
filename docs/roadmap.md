# Vybe roadmap

The checklist behind `/progress`. Tick a box when the work is on `main` and working.
Put `(now)` after the milestone being worked on. Owners: (Claude), (Mistral), (Team).

## Foundations
- [x] App scaffold: FastAPI + React page (Claude)
- [x] Ruff, strict mypy, tests (Claude)
- [x] AGENTS.md, README pitch, partner brief (Claude)

## Feed and ranking
- [x] Swipe-up/down full-screen cards (Claude)
- [x] Setup (budget, student, 18+) and likes saved in the browser (Claude)
- [x] Ranking: open soon, budget, 18+, badges, leave-by (Claude)
- [x] Google rating and personal match % shown separately (Claude)
- [x] Weather (rain and cold) in the match (Claude)

## Real places
- [x] Google Places near the user (Claude)
- [x] Browser location or typed postcode/area (Claude)
- [x] OpenStreetMap and sample-data fallback (Claude)

## Voice (now)
- [x] `audio_to_filters`: Voxtral turns speech into filters (Mistral)
- [ ] `POST /api/voice` with session-only filters (Claude)
- [ ] Ranking applies voice filters (Claude)
- [ ] Hold-to-talk button and filter chips (Claude)

## Background refresh
- [ ] Pipeline v1: Workflow fetches venues and writes `data/enriched.json` (Mistral)
- [ ] Enricher and Verifier agents (Mistral)
- [ ] Scout agent for tonight's events and deals (Mistral)
- [ ] Feed merges enriched deals, student prices and new events (Claude)
- [ ] Voxtral TTS voiceovers (Mistral)
- [ ] `/vybe` skill triggers a refresh (Mistral)

## Design
- [ ] Figma For You card applied (Claude)
- [ ] Details page (Claude)
- [ ] Voiceover playback with mute (Claude)

## Demo
- [ ] Time travel control (Claude)
- [ ] "Run refresh now" button, new card arrives live (Claude)
- [ ] HTTPS via cloudflared for phones (Claude)
- [ ] Backup: cached data and a recorded video (Team)
- [ ] Demo run-through (Team)
