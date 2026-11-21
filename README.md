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

## Deploy staging with Railway and Vercel

1. In Railway, deploy this repository as a service from the repository root. The start command in
   `railway.toml` runs FastAPI on Railway's port. Generate a public domain under Networking.
2. Set `MISTRAL_API_KEY` and optionally `GOOGLE_PLACES_API_KEY` in Railway's service variables.
3. In Vercel, import the repository with `web` as the root directory and use the Vite preset.
   Set `VITE_VYBE_WS_URL` in the Preview environment to the full socket URL, for example
   `wss://your-service.up.railway.app/ws`. Deploy or redeploy the preview to bake in the URL.
4. Open the preview with `/?reset`, join the board, change a filter, and verify the browser
   connects to the Railway socket and receives board updates.

## Deploy production from GitHub Actions

Pull requests targeting `main` run the Python tests and frontend build. A push to `main`
runs the same checks, prepares the Vercel production build, deploys the backend to Railway,
and publishes the Vercel build after Railway reports success.

Before merging the workflow:

1. Create a Railway production service in the repository root and give it a public domain.
   Disable Railway's GitHub autodeploy for that service. Keep app secrets in Railway.
2. Configure the Vercel project with the Vite preset and `web` as its root directory.
   Set its **Production** `VITE_VYBE_WS_URL` to `wss://<railway-domain>/ws`.
   The [Vercel config](web/vercel.json) disables Git-driven deployments from `main`.
3. In GitHub, create a `production` environment and restrict deployments to `main`.
   Add `RAILWAY_TOKEN` (a Railway production project token) and `VERCEL_TOKEN` as secrets.
   Add `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID`, `VERCEL_ORG_ID` and
   `VERCEL_PROJECT_ID` as variables.
4. After the first production run succeeds, open Vybe and join the board. In browser
   DevTools, confirm the Railway `/ws` request returns `101 Switching Protocols` and
   receives board updates when you change a filter.
