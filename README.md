# Vybe

Vybe shows you what's worth doing near you in the next few hours, best first.

It reads like a station departures board. Each place has a time, a walk, and when you need to leave to make it. The top three picks sit at the top, and everything else is listed by when you'd have to set off. Tap one to open it, then swipe up for the next.

Tell it what you're after, out loud or by typing: *"me and two mates, want a laugh, nothing over a tenner."* The board re-ranks straight away. What you say only lasts for this visit and isn't saved.

## What it does

Every place gets a status (on time, boarding, last call) and a leave-by time, worked out from its closing time and how far you have to walk. You can browse by Food, Drinks, Entertainment, Culture or Outdoors.

It respects your budget and student prices, and hides anything 18+ if you're under 18. Each card shows its Google rating and a match percentage for you, with up to three plain reasons, such as "Short walk" or "Top rated ★4.7".

There's no sign-up. Your settings and saved places stay in your browser. Save something and similar places move up; mark "Not for me" and it drops off the board.

Each venue's card takes its colours from the venue's own website, so a place with a red brand gets a red glow.

## Powered by Mistral

A Mistral Workflow refreshes venues, events and deals a few times a day. Inside it, a Scout agent looks for tonight's events and deals. An Enricher turns each venue into a card with a short voiceover script and its brand colour. A Verifier drops fake discounts and wrong prices before anyone sees them.

Voxtral handles voice. It turns what you say into filters for the board, and it reads out the voiceovers.

Built with the Mistral Vibe CLI for the Mistral Vibe Hackathon 2026, London.

## Tech

FastAPI · WebSocket · React · TypeScript · Vite · Google Places · Mistral Workflows, Agents SDK, Voxtral
