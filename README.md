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

A Mistral Workflow refreshes venues, events and deals a few times a day. Inside it, a Scout agent looks for tonight's events and deals. An Enricher turns each venue into a card with a short voiceover script and its brand colour. A Verifier drops fake discounts and wrong prices before anyone sees them.

Voxtral handles voice. It turns what you say into filters for the board, and it reads out the voiceovers.

Built with the Mistral Vibe CLI for the Mistral Vibe Hackathon 2026, London.

## Tech

FastAPI · WebSocket · React · TypeScript · Vite · Google Places · Mistral Workflows, Agents SDK, Voxtral

## Deploy to Railway

Railway runs one service for Vybe. The Docker build compiles the Vite frontend and
copies it into the FastAPI image. FastAPI serves the frontend at `/` and the
WebSocket at `/ws` on the same domain.

1. Connect the `jxcg/Vybe` GitHub repository to a Railway service in the
   `production` environment. Set its deployment branch to `main` and leave the
   root directory at the repository root. Clear any old start-command override
   so Railway uses the Dockerfile command.
2. Under **Settings → Networking**, generate a public domain. In the service's
   **Variables** tab, set `MISTRAL_API_KEY` for voice and optionally
   `GOOGLE_PLACES_API_KEY` for Google Places.
3. Keep Railway's GitHub autodeploy enabled. Once the CI workflow is present on
   `main`, enable **Wait for CI** in the service settings so Railway waits for the
   tests and production image build to pass before deploying subsequent pushes.
4. Open the Railway URL, join the board, and change a filter. In browser
   DevTools under **Network → WS**, confirm that the same-domain `/ws` request
   returns `101 Switching Protocols` and receives board updates.
