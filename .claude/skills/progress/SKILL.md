---
name: progress
description: Progress update for the Vybe project, with progress bars for the whole project and the current milestone, plus what's happening now, what's next and anything blocked. Use whenever the user asks where we are, what stage we're at, how far along we are, what's done or left, for a status or progress update, "/progress", or anything like "how's it going" or "what's Mistral doing", even if they don't say "progress".
---

# Progress update

Give the user a quick, honest picture of where Vybe is. This is a hackathon, so they want to glance at it and get back to work: bars first, a few short lines, no essays.

## 1. Gather the facts

Run these from the repo root (in parallel where you can):

- `git pull -q --rebase` (or `git fetch` if there are local changes), then `git log --oneline -15`. These are recent commits from Claude and Mistral.
- `git status --short`. Uncommitted work in progress shows up here.
- `cat docs/handoff.md` if it exists. It has Mistral's status, requests and blockers.
- `cat docs/roadmap.md`. This is the checklist the percentages come from.

## 2. Bring the roadmap up to date

The bars are only as true as `docs/roadmap.md`, so check it against what you just saw before running the script.

- **Tick** a task (`- [x]`) only when the work is on `main` and actually works, for example a commit plus passing tests. Something that's half-built or uncommitted stays unticked; mention it as "in progress" instead. An inflated bar is worse than a slow one, because the team plans around it.
- **Move `(now)`** to the milestone the team is actively working on.
- **Add** a task if real work has started that isn't on the list, under the milestone it belongs to, with an owner. Don't reword or delete tasks other people wrote.
- If you changed the roadmap, commit it: `docs: update roadmap progress`, then push to `main`, following `AGENTS.md`.

## 3. Draw the bars

```bash
python3 .claude/skills/progress/scripts/progress.py docs/roadmap.md
```

The script prints the overall bar, the current milestone's bar, a bar per milestone, and the current milestone's tasks. Paste its output **as is** inside a code block. Don't redraw or round the numbers yourself, so they match from one update to the next.

## 4. Write the update

Use this shape, and keep each section to one to three short bullets:

````markdown
```
<script output>
```

**Where we are:** <stage in plain words, e.g. "Core app works on real data; starting voice.">

**Doing now:**
- Claude: <what, and how far, e.g. "wiring /api/voice: route done, ranking next">
- Mistral: <from handoff.md and its commits>

**Next:** <the next 1–2 tasks>

**Blocked / needs you:** <anything waiting on the user, e.g. a key or a decision, or "Nothing">
````

Notes:
- Name who owns each piece (Claude, Mistral, Team) so the user knows who to chase.
- If Mistral has no commits and no handoff updates for a while, say so plainly. It may be stuck or waiting on approval.
- If anything in the repo is broken (failing tests, merge conflicts), put it first under "Blocked".
- Skip a section's bullets rather than padding it.
