# CLAUDE.md

Project context for Claude Code. Read this first, every session.

## What this is

Relay is a **human-gated networking outreach orchestrator**. Point it at a company +
role; it finds the right people, enriches their emails, drafts cold outreach in the
user's voice, drops drafts into Gmail, and tracks the funnel through to "did they
respond / what did we discuss." Full spec: `docs/PRD.md` (read §3, §5, §6 before
working on any stage).

**Job discovery (N-1) has been pulled forward** and is now Relay's entry point: from a
résumé + typed preferences it finds ranked internships across ~50 target companies
(via official ATS APIs), the user checks which to pursue, and the existing networking
flow runs per pursued company. Resume tailoring is still Phase 2 and NOT in scope.

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
  - `config.py` — env loading + adapter modes (jobs, Apollo, tracker, fit floor).
  - `outreach.py` — the voice rules, encoded once.
  - `resume.py` — résumé PDF → `Profile` (name/schools/major) (N0).
  - `jobs.py` — job discovery adapters: ATS APIs (Greenhouse/Lever/Ashby/Workday) +
    JobSpy + fixtures. Companies live in `targets.yml` (N-1).
  - `discover.py` — derive search terms + transparent fit-scoring/ranking (N-1).
  - `apollo.py` — people search + enrichment (N2, N3).
  - `gmail.py` — create drafts, never send (N5).
  - `sheets.py` — tracker; `Tracker` Protocol (local xlsx default, Google Sheets stub).
  - `flow.py` — orchestration shared by the launcher + CLI.
  - `gui.py` + `Relay.pyw` — tkinter desktop launcher.
  - `xlsx_checkbox.py` — render boolean gate cells as native Excel checkboxes.
  - `cli.py` — thin deterministic entry points.

## Conventions

- Python 3.11+, type hints everywhere, pydantic for data. Keep functions small and pure.
- Integration adapters stay swappable — code to the interface (e.g. the `Tracker`
  Protocol), not a concrete backend.
- Secrets come from `.env` (see `.env.example`); never hardcode keys or commit them.
- Prefer editing existing stubs over adding new files; keep the layout in `README.md` true.

## Status & next step

- **M0 (done):** scaffold — models, stubs, skill-commands, docs.
- **M1 (done):** `apollo.search_people` + `apollo.enrich` + `sheets.py`; `relay find`
  returns a ranked, enriched contact list to the Contacts tab (fixtures without a key).
- **N-1 job discovery (done):** `jobs.py` + `discover.py` + `flow.py` + `gui.py`.
  ~50 companies in `targets.yml` across Greenhouse/Lever/Ashby/Workday, parallel fetch,
  fit-scoring weighted by typed preferences + major + recency + preferred locations,
  duplicate collapse, clickable URLs, and a twice-daily Windows refresh task.
- **Next:**
  - **M2 — drafts → Gmail (N5):** `/draft-outreach` + `gmail.py` create-draft, gated on
    `want_to_message`. Must obey `outreach.py` and the referral rule.
  - **Real people search:** `apollo.py` live mode needs `APOLLO_API_KEY` (fixtures today).
  - **M3 — tracking + project suggester (N6/N7):** `/log-chat`, `/suggest-project`.
  - **Google Sheets backend:** implement `SheetsTracker` (currently a NotImplemented stub).
- **Golden-rule reminder for any new work:** every stage stays human-gated; no LinkedIn
  scraping; drafts obey `outreach.py`; never name an uncleared referrer.
