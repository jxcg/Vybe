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
- [ ] Open the board on a saved interest, group additional results, and mark short lists (Team)
- [ ] Keep runner-up and wildcard details visible on desktop cards (Team)
- [ ] Show compact venue ratings out of ten on board picks and activity rows (Team)
- [ ] Show only the best pick above the list when four activities are available (Team)
- [ ] Hide the sidebar panel when there are no additional activities (Team)

## Real places
- [x] Google Places near the user (Claude)
- [x] Browser location or typed postcode/area (Claude)
- [x] OpenStreetMap and sample-data fallback (Claude)

## Voice
- [x] `audio_to_filters`: Voxtral turns speech into filters (Mistral)
- [x] Voice over `/ws`: speech or typing becomes session-only chips (Claude)
- [x] Ranking applies voice filters (Claude)
- [ ] Mic capture in the web frontend, sending PCM to `/ws` (Team)
- [ ] Simplify mobile onboarding and enlarge voice and typing controls (Team)
- [ ] Open the board when Enter submits a typed prompt (Team)
- [ ] Open board settings from one full-width Change your vibe button (Team)
- [ ] `text_to_filters` and transcripts from Voxtral (Mistral)

## Background refresh
- [ ] Pipeline v1: Workflow fetches venues and writes `data/enriched.json` (Mistral)
- [ ] Enricher and Verifier agents (Mistral)
- [ ] Scout agent for tonight's events and deals (Mistral)
- [ ] Feed merges enriched deals, student prices and new events (Claude)
- [ ] Voxtral TTS voiceovers (Mistral)
- [ ] `/vybe` skill triggers a refresh (Mistral)

## Design (now)
- [ ] Render cached photo and gradient themes and verify the Studio debate (Team)
- [ ] Keep compact card text legible beneath bright venue photos (Team)
- [ ] Lead featured cards with venue names and give photos dedicated space (Team)
- [ ] Review Google Places photos in the theme workflow and derive card colours from the displayed photo (Team)
- [x] Teammate's VYBE frontend merged, with the `/ws` backend (Claude)
- [x] Light mode as primary, venue-colour glow on cards (Claude)
- [ ] Brand colours from each venue's website (Mistral)
- [ ] Location from the browser sent to `/ws` (Team)
- [ ] Voiceover playback with mute (Claude)

## Demo
- [ ] Deploy Vybe to Railway automatically from main (Team)
- [ ] Verify the Railway frontend connects to the same-domain WebSocket (Team)
- [ ] Verify the Railway deployment on a phone (Team)
- [ ] Time travel control (Claude)
- [ ] "Run refresh now" button, new card arrives live (Claude)
- [ ] HTTPS via cloudflared for phones (Claude)
- [ ] Backup: cached data and a recorded video (Team)
- [ ] Demo run-through (Team)
