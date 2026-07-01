# CLAUDE.md

Project context for Claude Code. Read this first, every session.

## What this is

Relay is a **human-gated networking outreach orchestrator**. Point it at a company +
role; it finds the right people, enriches their emails, drafts cold outreach in the
user's voice, drops drafts into Gmail, and tracks the funnel through to "did they
respond / what did we discuss." Full spec: `docs/PRD.md` (read §3, §5, §6 before
working on any stage).

**This is v1 — the networking layer only.** Job discovery and resume tailoring are
Phase 2 and are NOT in scope. Don't build them unless asked.

## Golden rules (do not violate)

1. **Human gate at every stage.** Relay prepares; the user approves. Never auto-send an
   email, never auto-submit an application. `gmail.py` creates DRAFTS only — never call
   a send endpoint.
2. **No LinkedIn scraping.** People are found via Apollo (org + title + school). LinkedIn
   is a manual eyeball step only. Don't add scraping.
3. **Outreach rules are law.** Every generated draft must follow `src/relay/outreach.py`
   (`OUTREACH_RULES`) — individual-specific hook over company enthusiasm, short, no
   referral ask on first contact, no aerospace/Boeing background in cold emails, no GPA,
   the banned "no agenda" line, anchored to business-operations process improvement.
   These rules live in exactly one place; reference them, don't restate or drift.
4. **Never name an uncleared referrer.** If `Contact.why == referral` and
   `referral_cleared` is false, skip drafting and flag it.

## Architecture

- **Orchestration** lives in `.claude/commands/` — one skill-command per pipeline stage
  (`find-people`, `draft-outreach`, `log-chat`, `suggest-project`). LLM-heavy work
  (hooks, drafts, project ideas, ranking) belongs here.
- **Deterministic code** lives in `src/relay/`:
  - `models.py` — pydantic schema, mirrors the tracker tabs. Source of truth for shape.
  - `outreach.py` — the voice rules, encoded once.
  - `resume.py` — resume PDF → `Profile` (N0).
  - `apollo.py` — people search + enrichment (N2, N3).
  - `gmail.py` — create drafts, never send (N5).
  - `sheets.py` — tracker via Google Sheets; `Tracker` Protocol allows a local-xlsx swap.
  - `cli.py` — thin deterministic entry points.

## Conventions

- Python 3.11+, type hints everywhere, pydantic for data. Keep functions small and pure.
- Integration adapters stay swappable — code to the interface (e.g. the `Tracker`
  Protocol), not a concrete backend.
- Secrets come from `.env` (see `.env.example`); never hardcode keys or commit them.
- Prefer editing existing stubs over adding new files; keep the layout in `README.md` true.

## Status & next step

- **M0 (done):** scaffold — models, stubs, skill-commands, docs.
- **M1 (next):** implement `apollo.search_people` + `apollo.enrich` and wire `sheets.py`
  so `/find-people` on "SpaceX Starlink, Business Operations Co-Op" returns a ranked,
  enriched contact list written to the Contacts tab. That's the smallest useful demo.
- Then M2 (drafts → Gmail), M3 (tracking + project suggester). See `docs/PRD.md` §8.
