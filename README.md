# Relay

A human-gated networking outreach orchestrator. Point it at a company + role; it finds
the right people (alumni, similar-role, referrals), enriches their emails, drafts cold
outreach in your voice that follows your playbook, drops them into your Gmail drafts to
edit and send, and tracks the funnel through to "did they respond / what did we discuss."

**It prepares; you approve.** Nothing sends or submits on its own.

This is **v1: the networking layer.** Job discovery + resume tailoring are Phase 2.
See [`docs/PRD.md`](docs/PRD.md).

## Quickstart

```bash
git clone <your-repo-url> relay && cd relay
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # fill in APOLLO_API_KEY, Google creds, SHEETS_WORKBOOK_KEY
```

Then open in Claude Code and run the stages as skill-commands:

```
/find-people        # discover + enrich contacts for a target  -> Contacts tab
# ...check who you want to message in the tracker...
/draft-outreach     # drafts for checked contacts -> your Gmail drafts
/log-chat           # record what happened after a conversation
/suggest-project    # portfolio project ideas + a ready-to-build PRD prompt
```

## Run it now (M1: N0–N4)

The find/enrich/track spine runs today. With **no Apollo key** it uses built-in
SpaceX/Starlink fixtures, so you can see the whole flow end to end; add
`APOLLO_API_KEY` to hit the real API. The tracker is a local `relay.xlsx` — no
Google credentials needed.

```bash
relay profile resume.pdf                     # N0: parse resume -> profile.json
relay target "SpaceX" "Business Operations Co-Op"   # N1: define the target
relay find "SpaceX" "Business Operations Co-Op"     # N2–N4: search + enrich + rank
relay contacts                               # show the Contacts tab
```

`relay find` writes ranked contacts (alumni + similar-role first, per PRD §5) to the
Contacts tab with `want_to_message` **unchecked**. Re-running it refreshes discovery
data without clobbering the boxes you've checked. Modes are set in `.env`
(`RELAY_APOLLO_MODE`, `RELAY_TRACKER_BACKEND`).

## Layout

```
docs/PRD.md            product spec (read this first)
.claude/commands/      Claude Code skill-commands — the orchestration, one per stage
src/relay/
  models.py            pydantic schema (mirrors the tracker tabs)
  config.py            env loading + adapter modes (Apollo mode, tracker backend)
  outreach.py          the outreach voice rules, encoded once
  resume.py            resume PDF -> Profile (N0)
  apollo.py            people search + email enrichment (live httpx + fixtures)
  pipeline.py          N2–N4 spine: search -> enrich -> rank (§5)
  gmail.py             create drafts (never sends)
  sheets.py            tracker storage (local .xlsx default; Google Sheets swappable)
  cli.py               deterministic helpers
```

## Principles

- Human gate at every stage. No auto-send, no auto-submit.
- No LinkedIn scraping — Apollo finds people by org + title + school instead.
- Drafts are barebones and in your voice, meant to be edited, not shipped as-is.
