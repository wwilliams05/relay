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

## Layout

```
docs/PRD.md            product spec (read this first)
.claude/commands/      Claude Code skill-commands — the orchestration, one per stage
src/relay/
  models.py            pydantic schema (mirrors the tracker tabs)
  outreach.py          the outreach voice rules, encoded once
  resume.py            resume PDF -> Profile
  apollo.py            people search + email enrichment
  gmail.py             create drafts (never sends)
  sheets.py            tracker storage (Google Sheets; local .xlsx swappable)
  cli.py               deterministic helpers
```

## Principles

- Human gate at every stage. No auto-send, no auto-submit.
- No LinkedIn scraping — Apollo finds people by org + title + school instead.
- Drafts are barebones and in your voice, meant to be edited, not shipped as-is.
