# Vybe

Vybe shows you what's worth doing near you in the next few hours, best first.

It reads like a station departures board. Each place has a time, a walk, and when you need to leave to make it. The top three picks sit at the top, and everything else is listed by when you'd have to set off. Tap one to open it, then swipe up for the next.

Tell it what you're after, out loud or by typing: *"me and two mates, want a laugh, nothing over a tenner."* The board re-ranks straight away. What you say only lasts for this visit and isn't saved.

## What it does

Every place gets a status (on time, boarding, last call) and a leave-by time, worked out from its closing time and how far you have to walk. You can browse by Food, Drinks, Entertainment, Culture or Outdoors.

It respects your budget and student prices, and hides anything 18+ if you're under 18. Each card shows its Google rating and a match percentage for you, with up to three plain reasons, such as "Short walk" or "Top rated ★4.7".

There's no sign-up. Your settings and saved places stay in your browser. Save something and similar places move up; mark "Not for me" and it drops off the board.

Venue cards use colours sourced from each venue's website where available.

## Powered by Mistral

- **Area refresh (`vybe-refresh`)** fetches venues, runs Scout, Enricher and Verifier, and saves verified event and deal details.
- **Venue themes (`vybe-theme` and `vybe-theme-item`)** choose photos and colours in the background. The area refresh starts this workflow.
- **Voxtral voiceovers (`vybe-voiceover`)** generate short venue clips after the theme workflow. Surprise me and the ticket's play button share the cached clips. Surprise me rotates through short Oliver lines for the activity’s category when a venue clip is unavailable or was just played.

The board ranks and selects activities in code. Voxtral also turns spoken requests into filters.

Built with the Mistral Vibe CLI for the Mistral Vibe Hackathon 2026, London.

## Tech

FastAPI · WebSocket · React · TypeScript · Vite · Google Places · Mistral Workflows, Agents SDK, Voxtral

## Deploy to Railway

Railway runs one service for Vybe. The Docker build compiles the Vite frontend and
copies it into the FastAPI image. FastAPI serves the frontend at `/` and the
WebSocket at `/ws` on the same domain.

### How deploys work

1. When you open or update a pull request, GitHub Actions runs the tests and builds the Docker image.
2. When you merge into `main`, GitHub Actions checks the merged commit. With **Wait for CI** enabled, Railway deploys it once the checks pass.

Railway uses its GitHub integration. GitHub Actions does not need a Railway token or project ID.

### Railway setup

1. Connect the `jxcg/Vybe` GitHub repository to a Railway service in the
   `production` environment. Set its deployment branch to `main` and leave the
   root directory at the repository root. Clear any old start-command override
   so Railway uses the Dockerfile command.
2. Under **Settings → Networking**, generate a public domain. In the service's
   **Variables** tab, set `MISTRAL_API_KEY` for voice and optionally
   `GOOGLE_PLACES_API_KEY` for Google Places.
3. Keep Railway's GitHub autodeploy enabled. Once the CI workflow is present on
   `main`, enable **Wait for CI** in the service settings.
4. Open the Railway URL, join the board, and change a filter. In browser
   DevTools under **Network → WS**, confirm that the same-domain `/ws` request
   returns `101 Switching Protocols` and receives board updates.
