# /draft-outreach — generate drafts for checked contacts (N5)

Read `src/relay/outreach.py` — the rules there are HARD constraints. Read them in full
before writing anything.

**Do:**
1. Read the Contacts tab (`relay.sheets.get_tracker().read_contacts()`); take only rows
   where `want_to_message` is checked and `draft_created` is not.
2. For each, if `why == referral` and `referral_cleared` is false, SKIP and flag it —
   do not name an uncleared referrer.
3. Write the draft yourself using `relay.outreach.draft_prompt(...)` as the brief. Open
   with the recipient-specific hook. Keep it brief. Barebones, in his voice — something
   to edit, not a finished product. (`relay.outreach.build_draft` is the deterministic
   template the CLI uses; you should do better, but never looser.)
4. Check your draft with `relay.outreach.lint_draft(subject + "\n" + body)` — it must
   return `[]`. Fix anything it flags before creating the draft.
5. Create it as a DRAFT via `relay.gmail.create_draft(contact, subject, body)` — never
   send. Set `draft_created` and persist with `tracker.update_contact(contact)`.

The whole loop above is also available as one call — `relay.flow.draft_outreach(profile)`
— when template drafts are good enough (that's what `relay draft` and the GUI button run).

**Self-check before each draft (per §6):** individual hook, not company enthusiasm ·
short · no referral ask on first contact · no Boeing/aerospace background · no GPA ·
no banned "no agenda" line · anchored to business-operations process improvement.

**Gate:** the user edits and sends every draft themselves. Fixture mode (no Google
credentials) writes .eml files to `drafts/` instead — same gate applies.
