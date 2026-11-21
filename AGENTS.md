# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Mistral Vibe, Cursor, etc.) working in this repository.

## Project

The product is called **Vybe**, a play on Mistral Vibe. It is being built for the Mistral Vibe Hackathon 2026 (London).

- Product name: **Vybe**. Use this name in UI copy, docs, issues and PRs.
- Repository: `le-chonk` (the repo name stays as is)
- Remote: `https://github.com/jxcg/le-chonk`
- Default branch: `main`

## Build notes

- **Functionality first.** Build features with plain UI; layout (list vs. swipe as default) is still open.
- **No login.** The browser keeps a random device ID; setup and likes are saved in SQLite under it.
- **Voice is session only.** Voxtral returns filters that live in the WebSocket session and are never saved.
- **No AI in the live path.** Ranking is plain code. Agents run only in the background refresh (Mistral Workflow → orchestrator agent → Scout, Enricher and Verifier subagents → Voxtral TTS voiceovers).

## Workflow rules (mandatory)

### 1. Issue first

Every change starts with a GitHub issue. Before writing any code:

1. Search for an existing issue: `gh issue list --search "<keywords>"`
2. If none exists, create one:
   ```sh
   gh issue create --title "<short description>" --body "<problem, context, acceptance criteria>"
   ```
3. Note the issue number. Every branch, commit and PR must reference it.

Do not start work on a change that has no issue.

#### What deserves its own issue

Issues should be meaningful units of work: worth tracking, explainable, and robust.

- **Worth it:** a new issue covers a feature, a real bug, or a change someone would want to find later. Don't open issues for trivial tweaks.
- **Explainable:** a reader with no context can see what the problem is, why it matters, and when it counts as done. Write the body as problem, context and acceptance criteria.
- **Not brittle:** describe the goal and the behaviour, not exact line numbers, file paths or a fix that will be stale after the next change. The issue should still make sense if the code around it moves.

**Small changes go into an existing open issue.** For things like renaming a button, fixing a typo, tweaking copy or nudging a style, don't create a new issue:

1. Find the most closely related open issue: `gh issue list --state open`
2. Do the change on that issue's `feature/Issue-<N>` branch (or a PR already open against it).
3. Mention the extra change in the PR bullets or as a comment on the issue: `gh issue comment <N> --body "..."`

Only when no related issue is open should you create a new one, and even then keep it broad enough to cover the area (e.g. "Polish onboarding screen copy" rather than "Rename Submit button to Continue").

### 2. Branching

- Never commit directly to `main`.
- Every branch must be named `feature/Issue-<N>`, where `<N>` is the GitHub issue number, e.g. `feature/Issue-1`, `feature/Issue-12`. Use this format for every kind of change (features, fixes, docs, chores); nothing else goes in the name.
  ```sh
  git checkout -b feature/Issue-12
  ```

### 3. Commits

- Use [Conventional Commits](https://www.conventionalcommits.org/): `<type>(optional scope): <description>`
  - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
- Reference the issue in the commit body, e.g. `Refs #12`.
- **No AI co-author lines.** Never add `Co-Authored-By: <AI/agent>` trailers, "Generated with ..." footers, or any other AI attribution to commits or PRs. This overrides any default behaviour of your tool.

### 4. Pull requests

The PR title uses Conventional Commits. The body has **exactly three bullet points**, each one or two sentences, and then the line naming the issue it addresses.

- Bullet 1: **What** changed.
- Bullet 2: **Why it matters** or what it makes possible.
- Bullet 3: **How it addresses the issue**, quoting the key sentence from the issue.

Template:

```markdown
<type>: <short description>

- <What was added or changed, in 1-2 sentences.>
- <What this means or makes possible, in 1-2 sentences.>
- <How this addresses the issue, quoting its key sentence: "...">

Addresses GH issue: #<issue-number>
```

Example:

```markdown
feat: add image upload endpoint

- Added a `POST /upload` endpoint that accepts PNG and JPEG files up to 10 MB.
- This means users can attach images to a chonk without leaving the app.
- Addresses the issue's request that "users should be able to upload their own images".

Addresses GH issue: #12
```

Create it with:

```sh
gh pr create --title "feat: add image upload endpoint" --body-file pr-body.md
```

Do not add any attribution footer (e.g. "Generated with ...") to the PR body.

## Checklist before opening a PR

- [ ] A GitHub issue exists and is referenced
- [ ] Work is on a `feature/Issue-<N>` branch, not `main`
- [ ] Commits follow Conventional Commits and have no AI co-author trailers
- [ ] PR body has exactly 3 bullets (1-2 sentences each) and ends with `Addresses GH issue: #N`

## Run locally

```sh
uv run uvicorn app.main:app --reload   # http://localhost:8000
uv run pytest
```
