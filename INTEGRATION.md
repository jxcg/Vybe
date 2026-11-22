# VYBE frontend ↔ backend integration

The frontend lives in `web/` (React + TS + Vite). It talks to the server over **one WebSocket** and renders
whatever the server sends. **The server is the source of truth**: the client never decides statuses, picks
or counts, it only displays them (it does advance the server's `now` locally between board messages for
countdowns).

## Run it against your server

```bash
cd web
npm install
VYBE_SERVER=http://localhost:8000 npm run dev   # proxies /ws to your server (default http://localhost:8000)
```

- Open `http://localhost:5173/?reset` (the `reset` clears saved state so you start from the start screen).
- `?mock` swaps the socket for an in-browser fake server, which is handy for comparing behaviour.
- Railway serves the frontend and `/ws` on the same domain. See [Railway setup](README.md#deploy-to-railway).

## Transport

- Path: **`/ws`**, on the configured backend or the page origin by default.
- **Text frames = JSON**, one message per frame, each with a `type` field.
- **Binary frames = mic audio** (coming in P4): mono **PCM16 little-endian at 16 000 Hz**, ~100 ms per
  frame, sent only between `talk_start` and `talk_end`.
- Reconnect: the client retries with exponential backoff (0.5 s → 15 s). On every reconnect it re-sends
  the session-only `location`, the last `prefs`, and either a fresh `join` (solo) or `room_resume` with the
  saved credential (shared plan).

All types are in [`web/src/contract.ts`](web/src/contract.ts). Times are **ISO 8601 strings with a timezone** (e.g.
`2026-11-21T19:30:00Z`). The UI shows them in Europe/London.

## Phone → server

| Message | When the client sends it |
|---|---|
| `{type:"join", room: string\|null, name?: string}` | On "See what's on" / "Skip" (first visit), and on every reconnect (solo) |
| `{type:"location", lat: number, lng: number, label: string}` | Session-only: browser geolocation, or the area/postcode the user picked. Sent before `join` once chosen, and again on every reconnect. Never persisted by the client |
| `{type:"prefs", budget: 10\|20\|999, student, adult, include: string[], exclude: string[], company: number}` | On **every** change to the user's vybe, right after `join`, and on reconnect. `company` = people including the user (1 = just me) |
| `{type:"talk_start", purpose:"mood"\|"command"\|"reason", item_id?}` | User taps the mic: `"mood"` on the start screen, `"command"` on the board. `"reason"` (+ `item_id`) is reserved and not sent yet |
| binary PCM frames | Between `talk_start` and `talk_end` (P4) |
| `{type:"talk_end"}` | User taps again, or after 15 s |
| `{type:"talk_text", text}` | Typed alternative to talking (900 ms after the user stops typing, or on Enter). Reply with `chips`, same as for speech |
| `{type:"feedback", item_id, kind:"like"\|"skip"}` | Bookmark / "Not for me" on a ticket |
| `{type:"board_on", item_id\|null}` | Reserved (P6 "I'm in" toggle): in the contract, not sent yet; the server ignores it |
| `{type:"time_travel", now: ISO}` / `{type:"refresh_now"}` | Demo panel (P5) |

⚠️ **Important:** the start screen sends `prefs`, `talk_start`, `talk_end` and `talk_text` **before** `join`
(the user builds their vybe first, then taps "See what's on"). Please accept these pre-join on the same
socket. If that's hard, tell us and the client will send `join` as soon as the socket opens instead.

## Server → phone

| Message | What the client does |
|---|---|
| `{type:"joined", room, you}` | Remembers `room` (saved, reused on reload and reconnect) |
| `{type:"board", now, area, weather:{summary, rain_from}, count, members, rows, boarded, decision}` | Replaces the whole board. Send after `join`, after every `prefs`, and whenever anything changes. Sending on a timer (every 10–30 s) is fine too; the mock sends every 2 s |
| `{type:"transcript", text, final}` | Live "You said …" under the mic. Send partials while talking, then `final:true` |
| `{type:"chips", include, exclude, budget?, student?, company?}` | **Merged** into the user's vybe (adds tags; a tag can't be in both lists; `budget`/`student`/`company` overwrite when present). The client then sends `prefs` back. The start screen shows "Got it…" until this arrives (8 s timeout) |
| `{type:"note", text}` | Shown as a 3 s toast, e.g. "Removed 2 outdoor, budget now under £10" |
| `{type:"announce", item_id, kind, url, caption}` | Reserved (P4 station voice): in the contract, not sent yet |
| `{type:"decision", item_id, by, plan:{leave_in_min, walk_min}}` | Reserved (P6): in the contract; `board.decision` is always `null` for now |

### `board` details that matter for the UI

- `count`: number of things still makeable (the headline "10 things…"). Usually = rows not `departed`/`cancelled`.
- `rows`: any order. The client groups non-picked rows into "Next 30 minutes" (by `leave_by`) and "Later".
- **Picks:** set `pick` on at most one row each for `"best"`, `"runner_up"` and `"wildcard"`. These become the
  hero cards and are not repeated in the list.
- **Status** is yours: `on_time | boarding | last_call | departed | delayed_rain | cancelled`.
  The mock uses: minutes until `leave_by` ≥20 on time, 5–20 boarding, 0–5 last call, <0 departed;
  outdoor + rain before the start → `delayed_rain`.
- **Departed rows:** keep sending them for a little while. The client shows "Departed" for 3 s, then collapses the row.
- `leave_by`: when to leave (the mock uses departure − walk − 5 min). Drives every countdown and the fuse line.
- `weather.rain_from`: ISO or `null`. Shows "rain from 19:30" / "raining now" under the headline.
- `area`: shown under the headline, e.g. "London Bridge".

### Row fields

```ts
{
  id, name, venue,
  category: "comedy"|"games"|"food"|"music"|"culture"|"bar"|"other",
  departure_time: ISO,
  departure_label: "Starts"|"Deal ends"|"Last entry"|"Kitchen closes",
  status, leave_by: ISO, walk_min: number,
  your_price: number|null,      // 0 shows "Free", null hides the price
  was_price: number|null,       // non-null + student pref shows "£8 student"
  score: 0-10,                  // ticket score ring "9/10 for you"
  pick: "best"|"runner_up"|"wildcard"|null,
  reasons: {icon, text}[],      // ≤3; icon = lucide name, see list below; the first one shows on the hero card
  photo_url: string|null,       // needs CORS (Access-Control-Allow-Origin) so the client can read its colour
  colors: {deep, soft, light}|null,  // hex; if null the client derives them from the photo or the category
  pitch, voiceover_url: string|null, booking_url: string|null,
  rating: number|null, lat, lng,
  source_url: string|null, checked_at: ISO
}
```

**Reason icons the client knows** (anything else falls back to a neutral icon):
`Footprints, Wallet, Laugh, Utensils, Clock, Music, Sparkles, Trophy, Users, Film, CloudRain, Palette, Dices,
Coffee, MicVocal, Star, Ticket, MapPin, Heart, Beer, Moon, Zap`

### Photos (`photo_url` + `colors`)

Photos make the hero cards and tickets. A bad photo is worse than none: with no photo the UI falls
back to a designed poster (big time on the venue colour), so only send a photo you're confident in.

1. **Source, in order:**
   1. The listing's own share image: `og:image` (or `twitter:image`) on the `source_url` page. Usually a
      deliberate shot of that exact event/venue.
   2. Fallback: a venue photo from Google Places Photos (show the required attribution) or Foursquare
      Places, matched by venue name + lat/lng.
   3. No stock or AI-generated images: they'd show a place that isn't the real one.
2. **Quality gate.** Reject anything that's not landscape, under ~800 px wide, or mostly text/logo/menu/
   flyer. A quick vision check works well, e.g. Pixtral: *"Is this an atmospheric photo of the place itself,
   with no large text or logos? Answer yes/no."*
3. **Process once, serve yourself.** Resize/crop to ~800×600 WebP, cache it, and serve it from **your own
   origin** (e.g. `/img/<id>.webp`). Fast on phones, stable URLs, and no hotlinking.
4. **Send `colors` with it.** Compute the venue colours from the same image server-side and send
   `colors: {deep, soft, light}` (hex). The client's rule: take the image's average colour, convert to
   OKLCH, keep the hue, and clamp: deep `L 0.30, C ≤ 0.055` · soft `L 0.42, C ≤ 0.055` · light `L 0.89, C ≤ 0.03`.
   If you skip this, the client extracts it itself, but then the image must allow CORS
   (`Access-Control-Allow-Origin`), otherwise it falls back to category colours.
5. If none of the above gives a good image: `photo_url: null`. The poster looks intentional.

For the mock/demo, drop ~10 landscape, text-free photos (e.g. Unsplash, free licence) into
`web/public/mock/` named after the mock items.

### Tag vocabulary (suggestions shown in the UI; other tags are fine and appear as chips)

- **Into:** `a laugh`, `chill`, `active`, `competitive`, `food`, `live music`, `culture`, `late night`
- **Not into:** `clubs`, `loud music`, `outdoors`, `late nights`, `queues`

Tags are lowercase; the UI capitalises them.

## Minimal `board` example

```json
{
  "type": "board",
  "now": "2026-11-21T18:45:00Z",
  "area": "London Bridge",
  "weather": { "summary": "Light rain", "rain_from": "2026-11-21T19:30:00Z" },
  "count": 1,
  "members": ["You"],
  "boarded": {},
  "decision": null,
  "rows": [{
    "id": "basement-stand-up", "name": "Basement Stand-Up", "venue": "The Arches Comedy Room",
    "category": "comedy", "departure_time": "2026-11-21T19:30:00Z", "departure_label": "Starts",
    "status": "on_time", "leave_by": "2026-11-21T19:19:00Z", "walk_min": 6,
    "your_price": 8, "was_price": 14, "score": 9.2, "pick": "best",
    "reasons": [{ "icon": "Laugh", "text": "Five new acts and a headliner" }],
    "photo_url": null, "colors": null, "pitch": "A brick-vaulted room under the tracks.",
    "voiceover_url": null, "booking_url": null, "rating": 4.6,
    "lat": 51.5039, "lng": -0.0858, "source_url": null, "checked_at": "2026-11-21T18:41:00Z"
  }]
}
```

## How it should behave, end to end

Each flow is the exact order of messages the phone sends (→) and what the server should answer (←).

### 1. Talking on the start screen (mood)

The user hasn't joined yet. They tap the mic, talk, tap again (or hit 15 s).

```
→ {"type":"talk_start","purpose":"mood"}
→ <binary PCM frames, ~100 ms each, 16 kHz mono PCM16 LE>      (P4)
← {"type":"transcript","text":"Me and two","final":false}         every ~300–500 ms while talking
← {"type":"transcript","text":"Me and two mates, want a laugh","final":false}
→ {"type":"talk_end"}
← {"type":"transcript","text":"Me and two mates, want a laugh, nothing over a tenner.","final":true}
← {"type":"chips","include":["a laugh"],"exclude":[],"budget":10,"company":3}   within ~1–2 s
→ {"type":"prefs", ...updated vybe...}                            the client echoes the merged result
```

- Partial transcripts make the "You said …" line update live. If your speech-to-text can't stream,
  send just the final one, but send it straight after `talk_end`.
- The UI shows "Got it…" from `talk_end` until `chips` arrives (gives up after 8 s). **Always send `chips`**,
  even empty (`{"type":"chips","include":[],"exclude":[]}`) if nothing was understood.

### 2. Typing instead

```
→ {"type":"talk_text","text":"something chill to eat, under £15"}
← {"type":"chips","include":["chill","food"],"exclude":[],"budget":20}
→ {"type":"prefs", ...}
```

Same interpretation as speech, minus the audio. It fires 900 ms after the user stops typing, so expect
a few in a row while they edit. Each one should return the chips for the **whole** text.

### 3. "See what's on" (or "Skip, show me everything")

```
→ {"type":"join","room":null}
→ {"type":"prefs", ...}
← {"type":"joined","room":"r_8f2k","you":"u_31"}
← {"type":"board", ...}                                           ASAP: the loading screen waits for it
```

"Skip, show me everything" sends prefs with `include:[]`, `exclude:[]`, `budget:999`.
After that, send a fresh `board` whenever anything changes (statuses tick over, new listings, weather), and
at least every ~30 s.

### 4. Talking to the board (command)

The user is on the board and says something like "cheaper, nothing outdoors" or "we're hungry".

```
→ {"type":"talk_start","purpose":"command"}
→ <binary PCM frames>
← {"type":"transcript", ... "final":false}
→ {"type":"talk_end"}
← {"type":"transcript","text":"cheaper, nothing outdoors","final":true}
← {"type":"chips","include":[],"exclude":["outdoors"],"budget":10}
← {"type":"note","text":"Removed 1 outdoor, budget now under £10"}
← {"type":"board", ...re-ranked...}
→ {"type":"prefs", ...}                                            echo of the merged vybe
```

- `note` is one short sentence saying **what changed** (shown as a 3 s toast). If nothing changed, say so:
  "Nothing cheaper is still on, showing what's left".
- The `prefs` echo arriving after your `board` is expected. If it matches what you already applied,
  don't re-rank again.

### 5. Turning speech into tags (rules for both `mood` and `command`)

| The user says… | Send in `chips` |
|---|---|
| "a laugh", "comedy", "something funny" | `include: ["a laugh"]` |
| "chill", "quiet", "relaxed" | `include: ["chill"]` |
| "eat", "hungry", "dinner", "food" | `include: ["food"]` |
| "gig", "live music", "jazz" | `include: ["live music"]` |
| "active", "bowling", "ping pong" | `include: ["active"]`, also `"competitive"` if they want to win something |
| "art", "gallery", "museum", "culture" | `include: ["culture"]` |
| "late one", "out late" | `include: ["late night"]` |
| "nothing outdoors", "not outside", "it's raining" | `exclude: ["outdoors"]` |
| "no clubs", "not loud", "no queues" | `exclude: ["clubs"]` / `["loud music"]` / `["queues"]` |
| "under a tenner", "cheap", "skint" | `budget: 10` |
| "under 15/20 quid" | `budget: 20` (anything ≤ £10 → 10, ≤ £20 → 20, more → 999) |
| "money's no object", "whatever" | `budget: 999` |
| "me and two mates", "three of us" | `company: 3` (count the user too) |
| "just me", "on my own" | `company: 1` |
| "I'm a student" | `student: true` |
| **command only:** "cheaper" | budget one step down (999 → 20 → 10) |
| **command only:** "forget the budget" | `budget: 999` |

- Prefer the vocabulary tags above (the UI has quick-pick chips for them). New lowercase tags are fine
  too, e.g. `"karaoke"`. They appear as chips and the user can remove them.
- Only send fields the user actually mentioned. Omitted `budget`/`student`/`company` keep their current values.
- The client **adds** your tags to the current vybe; a tag can't be both into and not-into (the newest wins).
  To remove a tag, put it on the other side (e.g. `include: ["outdoors"]` lifts an earlier exclude).

### 6. Announcements (the station voice)

Send an `announce` when one of the user's **picked** rows changes status:

| When | `kind` | Example caption |
|---|---|---|
| A pick goes `on_time` → `boarding` | `boarding` | "Basement Stand-Up is now boarding. Leave in 15 minutes." |
| A pick goes → `last_call` | `last_call` | "Last call for Basement Stand-Up. Leave now." |
| Group decision made (P6) | `doors` | "Doors closing. You're going to Basement Stand-Up." |

```json
{"type":"announce","item_id":"basement-stand-up","kind":"boarding",
 "url":"/audio/basement-stand-up-boarding.pcm","caption":"Basement Stand-Up is now boarding. Leave in 15 minutes."}
```

- **Audio format:** raw **PCM16 little-endian, mono, 24 000 Hz, no WAV header**. Serve it from the same
  origin (or with CORS). A calm British station-announcer voice, ≤ ~6 s.
- Once per row per `kind` (don't repeat on every board). The client plays one clip at a time and drops
  extras if more than 2 are queued, so don't burst.
- The caption is shown on screen while the clip plays, so make it match what's said.
- `voiceover_url` on a row (the ticket's speaker button) uses the same audio format.

### 7. Save and "Not for me"

```
→ {"type":"feedback","item_id":"basement-stand-up","kind":"like"}
→ {"type":"feedback","item_id":"basement-stand-up","kind":"skip"}
← {"type":"board", ...without that row, re-ranked...}   (a `note` toast is welcome but optional)
```

The client hides a skipped row immediately; your `board` should leave it out from then on, and use likes
and skips to re-rank.

### 8. Location (session-only)

```
→ {"type":"location","lat":51.5045,"lng":-0.0865,"label":"Near you"}
← {"type":"board","area":"Near you", ...walking times recomputed...}
```

The web client asks for the browser location first (area/postcode lookup if denied) and only then opens a
solo board; coordinates live in the WebSocket session only and are re-sent on reconnect. A bare `join`
with no prior `location` still gets a board at the server's default demo area.

### Backend "done" checklist

- [ ] `/ws` accepts `prefs`, `talk_*`, `talk_text` **before** `join`
- [x] `join` → `joined` + `board` within ~1 s; shared plans resume via `room_resume` + credential
- [ ] every `prefs` → re-ranked `board`
- [ ] speech: binary frames between `talk_start`/`talk_end` → partial + final `transcript` → `chips` (always)
- [ ] `talk_text` → `chips`
- [ ] `purpose:"command"` → `chips` + `note` + `board`
- [ ] statuses, `leave_by`, picks and `count` computed server-side; departed rows kept briefly
- [ ] `announce` when a pick turns boarding / last call, with PCM16 24 kHz mono audio
- [x] `feedback` skip removes the row for that user, like/skip re-rank (answered with a fresh `board`)
- [ ] photos: good or `null`, served from your origin, `colors` sent with them
- [x] `location` handled: validated, drives nearby search + weather, re-boards with the new `area`

## Open decisions (please reply)

1. **Pre-join messages:** OK to receive `prefs` / `talk_*` before `join`? (see ⚠️ above)
2. **Location:** resolved — see §8. `{type:"location", lat, lng, label}` is in the contract; the client sends
   it before `join` and on reconnect; the server replies with a fresh `board` whose `area` is the label.
3. **Groups (P6):** optional per-row `fits: string[]` (members it suits) and `clashes: {name, reason}[]`.
   Merge rules we're assuming: lowest budget wins, anyone's "not into" flags a row, shared "into" ranks higher,
   anyone under 18 removes adult-only places.

## Quick smoke test

1. Start your server with `/ws`, then run `VYBE_SERVER=http://localhost:<port> npm run dev`.
2. Open `http://localhost:5173/?reset`, type "something chill, nothing outdoors" (Type instead) → expect a
   `talk_text` frame, then your `chips` → chips appear in "Your vybe".
3. Tap **See what's on** → expect `join` + `prefs` → your `joined` + `board` → loading screen hands off to the board.
4. Kill the server: a "Reconnecting…" pill appears and the last board stays. Restart it: the client re-sends
   `join` (with the room) + `prefs` automatically.
