# Relay

A human-gated networking outreach orchestrator. Point it at a company + role; it finds
the right people (alumni, similar-role, referrals), enriches their emails, drafts cold
outreach in your voice that follows your playbook, drops them into your Gmail drafts to
edit and send, and tracks the funnel through to "did they respond / what did we discuss."

**It prepares; you approve.** Nothing sends or submits on its own.

**Job discovery is now the front door:** from your résumé + preferences it finds and
fit-ranks internships across ~50 companies (official ATS APIs — Greenhouse/Lever/Ashby/
Workday), you tick which to pursue, and the networking flow runs per company. Résumé
tailoring is still Phase 2. See [`docs/PRD.md`](docs/PRD.md).

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

## Launcher (easiest)

Double-click **`Relay.pyw`** (or run `relay ui`) to open a small window:

1. **Import PDF…** — pick your résumé.
2. **Looking for:** — type what's not on the résumé, e.g. *"Fall 2026 Co-Op, Product
   Management or BizOps"*. Press **Enter** or **① Find jobs ▶**.
3. Relay scrapes job boards, fit-ranks the matches, and opens the spreadsheet. Tick
   **`pursue`** on the jobs you want.
4. Back in the window, **② Find people for checked jobs** populates the Contacts tab.
   Tick **`want_to_message`**.
5. **③ Draft outreach for checked contacts** writes a short, rule-checked draft per
   checked contact — into your Gmail drafts (live) or as `.eml` files in `drafts/`
   (no Google credentials). Uncleared referrals are skipped and flagged, never named.

Everything else lives in the spreadsheet. Nothing sends on its own.

## Run it from the terminal (same flow)

Works with **no credentials**: job discovery falls back to sample postings and people
discovery uses SpaceX/Starlink fixtures. Add `APOLLO_API_KEY` for real people. Real
postings need no key — the default `auto` mode pulls live internships from target
companies' official ATS APIs (Greenhouse/Lever/Ashby/Workday, listed in `targets.yml`),
falling back to JobSpy board scraping then fixtures only if ATS comes up empty (so it
returns fast and never stalls on a blocked scrape). The tracker is a local `relay.xlsx`.

```bash
relay discover --notes "Fall 2026 Co-Op, PM or BizOps"   # N-1: scrape + fit-rank -> Jobs tab
# ...tick `pursue` on jobs in the spreadsheet...
relay find-checked                                       # N2–N4 for pursued jobs -> Contacts tab
relay contacts                                           # show the Contacts tab
# ...tick `want_to_message` on contacts...
relay draft                                              # N5: rule-checked drafts (never sends)
relay log "Elan" --messaged today --responded -m "..."   # N6: record what happened
relay projects && relay prd                              # N7: project ideas -> PRD prompts
relay status                                             # funnel counts + the next gate

# or drive a single company directly (skip job discovery):
relay find "SpaceX" "Business Operations Co-Op"
```

Contacts are ranked alumni + similar-role first (PRD §5) with `want_to_message`
**unchecked**. Re-running never clobbers boxes you've checked. Modes live in `.env`
(`RELAY_JOBS_MODE`, `RELAY_APOLLO_MODE`, `RELAY_GMAIL_MODE`, `RELAY_TRACKER_BACKEND`).
Without Gmail credentials, `relay draft` writes `.eml` files to `drafts/`; with the
compose-only OAuth client it creates real Gmail drafts. Either way you edit and send.

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Fully offline: every adapter runs in fixture mode against a temp workbook.

## Keep the Jobs tab fresh automatically (Windows)

`relay discover` with no arguments reuses your saved résumé + preferences, so a
scheduled task can refresh the Jobs tab on its own (fresher postings score higher —
applying early matters). Register a twice-daily (8am/6pm) run:

```powershell
$py = "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe"
$action  = New-ScheduledTaskAction -Execute $py -Argument "-m relay.cli discover" -WorkingDirectory (Get-Location)
$trigs   = @((New-ScheduledTaskTrigger -Daily -At 8:00AM), (New-ScheduledTaskTrigger -Daily -At 6:00PM))
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "RelayJobDiscovery" -Action $action -Trigger $trigs -Settings $set
```

Remove it with `Unregister-ScheduledTask -TaskName RelayJobDiscovery -Confirm:$false`.
This refreshes the 51 ATS/Workday companies with no Claude in the loop; pulling
Indeed/LinkedIn continuously needs the Google-Sheets + cloud-agent path (see PRD).

## Layout

```
docs/PRD.md            product spec (read this first)
.claude/commands/      Claude Code skill-commands — the orchestration, one per stage
targets.yml            ATS target companies for job discovery (edit to add your own)
Relay.pyw               double-click launcher (opens the GUI)
tests/                 offline pytest suite (fixture modes + temp workbook)
src/relay/
  models.py            pydantic schema (mirrors the tracker tabs)
  config.py            env loading + adapter modes (jobs, Apollo, Gmail, tracker)
  outreach.py          the outreach voice rules, encoded once + draft builder/lint (N5)
  resume.py            resume PDF -> Profile (N0)
  jobs.py              job discovery: ATS APIs (targets.yml) + JobSpy + fixtures (N-1)
  discover.py          derive search terms + fit-rank + cross-city dedupe (N-1)
  apollo.py            people search + email enrichment (live httpx + fixtures)
  pipeline.py          N2–N4 spine: search -> enrich -> rank (§5)
  flow.py              orchestration shared by the launcher + CLI (incl. N5–N7 + status)
  gui.py               tkinter launcher
  gmail.py             create drafts, never send (live Gmail or local .eml fixture)
  sheets.py            tracker storage (local .xlsx default; Google Sheets drop-in)
  xlsx_checkbox.py     turns boolean cells into native Excel checkboxes
  cli.py               deterministic helpers + command surface
```

## Principles

- Human gate at every stage. No auto-send, no auto-submit.
- No LinkedIn scraping — Apollo finds people by org + title + school instead.
- Drafts are barebones and in your voice, meant to be edited, not shipped as-is.
