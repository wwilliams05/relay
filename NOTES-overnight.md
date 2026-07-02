# Overnight buildout — 2026-07-02 (branch: `overnight-buildout`)

All five priorities landed, in order, each committed only when `python -m compileall`
and the full pytest suite were green. Nothing on `main` was touched. Everything was
built and verified in fixture mode — no paid API calls, nothing sent anywhere.

## What was built (one commit per unit)

1. **`d2a5973` — Test suite (P1).** `tests/` with 60 tests over the deterministic core:
   discover fit-scoring (role/major/location/recency weights, off-target penalty),
   jobs intern-title gate + `_to_date`/`_workday_posted_date`, LocalXlsxTracker
   round-trips (sort, sub-floor pruning, pursue/human-column preservation, checkbox
   injection), resume name/school/major heuristics. `pytest` added as a `dev` extra.
   Tests pin every mode to fixture and use a temp workbook, so the suite is offline.

2. **`7ffbff8` — M2: drafts → Gmail, N5 (P2).**
   - `gmail.py`: live/fixture/auto modes mirroring `apollo.py`. Fixture writes `.eml`
     files to `drafts/` (gitignored); live uses the **compose-only** OAuth scope and
     `users.drafts.create`. There is no send path — enforced by an AST-based test
     that fails if any `.send` attribute access appears in the module.
   - `outreach.py`: `lint_draft` encodes §6 as checks (banned "no agenda"/GPA/
     aerospace-Boeing content, first-contact referral asks, company-enthusiasm
     openers, >120 words); `build_draft` produces a deterministic, rule-checked
     (subject, body), prefers a skill-written `hook`, refuses uncleared referrals,
     and raises if a hook smuggles in banned content.
   - `flow.draft_outreach`: only `want_to_message` contacts; skips + flags uncleared
     referrals and no-email contacts; sets `draft_created`; idempotent re-runs.
   - Wired to `relay draft` and the GUI's step ③ (was a disabled placeholder).
   - `RELAY_PROFILE_PATH` added so tests/scheduled runs never clobber `profile.json`.

3. **`f710c6b` — M3 part 1: N6 + N7 (P3).** `flow.log_chat` (name resolution: exact,
   then unique-partial; loud errors on unknown/ambiguous; notes append across chats)
   as `relay log`. Projects tab became a real upsert (`project_key`, preserves the
   human `interested` tick, never clobbers an existing `prd_prompt`);
   `flow.add_projects` + `flow.fill_prd_prompts` + `outreach.project_prd_prompt`
   (weekend-scoped PRD prompt) as `relay projects` / `relay prd`. Skill-commands
   updated to call the deterministic spine.

4. **`a5aab60` — SheetsTracker (P4).** Upsert/merge semantics extracted into pure
   `merge_*` functions shared by both backends; `SheetsTracker` implements the full
   `Tracker` Protocol on gspread with lazy service-account auth
   (`GOOGLE_APPLICATION_CREDENTIALS`) and an injectable client — tests drive it
   against an in-memory fake that stringifies cells the way the real Sheets API does.
   Missing-creds path fails with setup guidance, tested without network.

5. **`7f2ca89` — Polish (P5).** Cross-city duplicate collapse (same company+role per
   city → best-scored copy wins, "+N more locations" note), Workday `locationsText`
   tidy-up, `relay status` (per-tab funnel counts + computed next human gate), clean
   one-line errors for `relay jobs` / `relay profile`.

Final state: **99 tests, all passing** (`pytest -q`), plus a manual fixture-mode
smoke of the full funnel: discover → tick pursue → find-checked → tick
want_to_message → draft (.eml created, uncleared referral flagged, no-email skipped)
→ re-draft (idempotent) → log → prd → status.

## Golden-rule compliance

- No send path exists in `gmail.py` (AST-tested); drafts only, in Gmail or `.eml`.
- Uncleared referrals are refused in `build_draft` *and* skipped+flagged in
  `flow.draft_outreach` (defense in depth), tested both places.
- No LinkedIn scraping added anywhere.
- `lint_draft` mechanically enforces the §6 rules on every deterministic draft; the
  /draft-outreach skill is instructed to run it on model-written drafts too.

## Decisions / assumptions

- **Deterministic drafts are templates.** The PRD says drafting is LLM-heavy skill
  work; `outreach.build_draft` is deliberately a barebones, rule-checked fallback so
  `relay draft` and the GUI work with no model in the loop. The skill writes better
  bodies; both paths go through the same lint.
- **`chat_notes` append** (with ` | `) rather than overwrite — a second chat should
  never silently erase the first. Pass `append_notes=False` to replace.
- **Cross-city collapse mutates `location` for display** ("Los Angeles, CA (+2 more
  locations)"); the kept row's URL is the best-scored city's posting.
- **Gmail live + Sheets live are implemented but unexercised** — no credentials here.
  Both fail loudly with setup instructions; optional deps live in the `gmail` extra.
- **Commit trailer:** the task asked for `Co-Authored-By: Claude Opus 4.8`, but this
  session actually ran on Claude Fable 5, so commits carry the accurate
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` instead of misattributing.

## What's left (in rough order)

- Live people search (`APOLLO_API_KEY`) — fixtures everywhere today.
- Dogfood Gmail OAuth (N5) and SheetsTracker against real credentials.
- `/find-people` skill should write per-contact `hook`s; the deterministic fallback
  only uses school/title facts.
- Phase 2 (resume tailoring / ATS pass) remains out of scope.
