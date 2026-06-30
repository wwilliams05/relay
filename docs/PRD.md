# Relay — PRD (v1: Networking Layer)

> Working name `relay`; rename freely. This is the v1 slice of a larger job-search
> orchestrator. v1 ships the part nothing else on the market does well: turning a
> target company into warm, personalized outreach you actually send.

## 1. Summary

Relay parses your resume and a target (company + role), finds the right people to
reach out to, enriches their contact info, drafts cold emails in your voice that
follow your outreach playbook, drops them into your Gmail drafts for you to edit and
send, and tracks the whole funnel through to "did they respond / what did we talk
about." It also suggests portfolio projects you could build to show specific contacts,
and hands you a ready-to-use PRD prompt to vibe-code each one.

Every stage is **human-gated**: Relay prepares, you approve. Nothing sends or submits
on its own.

**v1 dogfood target:** the live SpaceX Starlink Business Operations Co-Op campaign
(Business Ops / Supply Chain BizOps / Product Growth tracks), anchored to a single
throughline — *business operations process improvement* — so outreach reads coherent,
not scattered.

## 2. Goals / Non-goals

**Goals**
- Turn a target company into a ranked, enriched list of *the right* people (alumni,
  similar-role, mutual-connection) in minutes, not hours.
- Generate outreach that follows the playbook in §6 exactly — so drafts need light
  edits, not rewrites.
- Keep a single source of truth for the funnel: who to message → messaged → responded →
  chat notes → next step.
- Be clean, runnable, and documented enough to show in a portfolio or to a hiring manager.

**Non-goals (v1)**
- No job discovery / scraping job boards (Phase 2).
- No resume tailoring / ATS optimization (Phase 2).
- No auto-sending or auto-submitting — ever. Relay drafts; you send.
- No LinkedIn scraping while logged into your account (see §7).

## 3. Pipeline (v1)

Each stage: **input → action → output → your gate.**

| # | Stage | Action | Output | Gate |
|---|-------|--------|--------|------|
| N0 | Profile intake | Parse resume PDF → structured Profile (schools, roles, skills, anchor framing) | `Profile` object | Confirm parse looks right |
| N1 | Target intake | Define company + role + JD; set what "similar role" means | `Target` row | Confirm target |
| N2 | People discovery | Apollo people-search by org + titles + school; classify each by *why them* (alumni / similar-role / referral) | candidate `Contact` rows | — |
| N3 | Enrichment | Apollo enriches email + verifies; dedup | enriched `Contact` rows | — |
| N4 | Prioritize + select | Rank by hook strength; write to **Contacts** tab with a per-person hook and a `want_to_message?` checkbox | Contacts tab | **You check who to message** |
| N5 | Draft | For checked contacts, generate a barebones, in-your-voice email per §6 rules → drop into Gmail drafts | Gmail drafts + `draft_created` flag | **You edit + send yourself** |
| N6 | Track | Log `messaged` (date), `responded`, `chat_notes`, `next_step` back to the tracker | updated Contacts tab | **You update after each chat** |
| N7 | Project suggester *(fast-follow in v1)* | Suggest 2–3 projects to show a specific contact (e.g. a SQL/Starlink project for Elan); on selection, output a PRD prompt you can hand to an LLM | **Projects** tab + PRD prompt | **You pick the project** |

## 4. Data model (tracker tabs)

One workbook, multiple tabs. Schema mirrors `src/relay/models.py`.

**Targets** — `company`, `role`, `jd_url`, `anchor_framing`, `status`
**Contacts** — `name`, `title`, `company`, `profile_url`, `why` (alumni|similar_role|mutual|referral),
`school_match`, `email`, `email_status`, `hook`, `want_to_message` ☐, `referral_cleared` ☐,
`draft_created` ☐, `messaged_date`, `responded` ☐, `chat_notes`, `next_step`
**Projects** — `target_company`, `for_contact`, `project_idea`, `skills_shown`, `interested` ☐,
`prd_prompt`

(A **Jobs** tab is reserved for Phase 2; v1 doesn't write it.)

## 5. Prioritization logic (N4)

Rank candidates by hook strength, highest first:
1. **Referral** — someone already offered to refer you (and `referral_cleared` is true).
2. **Alumni + similar role** — USC / WashU *and* a BizOps/Supply-Chain/Product-Growth title.
3. **Alumni** — shared school, any relevant role.
4. **Similar role** — strong title match, no school overlap.

> **Mutual connections** are *not* auto-detected in v1 (that needs your LinkedIn graph,
> which we're deliberately not touching — see §7). The shortlist surfaces a manual
> "check LinkedIn for mutuals" prompt for the top N contacts instead.

## 6. Outreach Voice & Rules (the spec for N5 + N7)

These are hard constraints on every generated draft. They encode what's already working.

- **Lead with a genuine, individual-specific hook** — shared alma mater, a specific career
  transition, a public post, a role they moved into. **Never** open with broad enthusiasm
  for the company.
- **Short wins.** Shorter emails consistently outperform longer ones. Default to brief.
- **Barebones, in his voice** — produce a draft to *edit*, not a polished final. Preserve
  conversational honesty; don't over-polish.
- **No referral asks on first contact.** Build the relationship; a thank-you beats an ask.
  Referencing something a contact *offered first* (e.g. an intern opening) is fine;
  unsolicited asks are not.
- **Reserve the aerospace/Boeing family background for live conversations** — never put it
  in a cold email.
- **No GPA** in casual coffee-chat emails.
- **Verify before referencing** — only use a contact's name as a referral once cleared
  (`referral_cleared`); verify any specific claim (an article, a course) before it goes in.
- **Anchor to business-operations process improvement** so multi-track outreach reads as one
  coherent story.
- **Banned line:** never write "No agenda beyond hearing your perspective" or anything
  similar. It reads as filler and slightly suspicious.

## 7. Architecture & integrations

**Orchestration:** Claude Code drives the pipeline via skill-commands in `.claude/commands/`
(one per stage). The LLM-heavy bits — hook generation, draft writing, project ideation,
prioritization reasoning — live there. Thin Python in `src/relay/` handles parsing, the data
model, and the integration adapters.

**Integration adapters (swappable):**
- `apollo.py` — people search + email enrichment via Apollo REST API (you have the Apollo
  connector; v1 uses a direct client for a self-contained, runnable repo).
- `gmail.py` — create drafts via Gmail API.
- `sheets.py` — read/write the tracker via Google Sheets (gspread). Local `.xlsx` adapter is a
  drop-in alternative behind the same interface.

**On LinkedIn:** we deliberately avoid automated LinkedIn scraping. For *people*, Apollo
(filtered by org + title + school) returns alumni and similar-role contacts *with enriched
emails in one step* and near-zero account risk. LinkedIn stays a manual "eyeball this person /
check mutuals" step on the shortlist.

**Stack:** Python 3.11+, pydantic, httpx, pdfplumber, gspread + google-auth, typer, rich,
python-dotenv.

## 8. Milestones

- **M0 — Scaffold** (this repo): structure, models, adapter stubs, skill-commands, README.
- **M1 — Find + enrich + tracker:** N0–N4 working end to end; Contacts tab populates with hooks
  and checkboxes. *Demo: paste "SpaceX Starlink, Business Operations Co-Op" → ranked enriched list.*
- **M2 — Draft + Gmail:** N5; checked contacts produce in-voice drafts in your Gmail. *Demo:
  check 3 contacts → 3 drafts waiting to edit.*
- **M3 — Track + project suggester:** N6 + N7. Funnel logging + project ideas with PRD prompts.

## 9. Open decisions

- Apollo plan / monthly credit budget (enrichment costs credits).
- Gmail auth: OAuth desktop flow vs. workspace service account.
- Target companies beyond SpaceX to seed (each becomes a `Target` row).
- Whether to keep Sheets or flip to local `.xlsx` once you've used it for a week.

## 10. Phase 2 (reserved, not built in v1)

Job discovery (JobSpy via Indeed + ATS APIs: Greenhouse/Lever/Ashby), fit-scoring against your
resume, per-job resume tailoring + ATS keyword pass, and the Jobs tracker tab — all gated, none
auto-submitting. The networking layer becomes the warm-intro engine that sits in front of it.
