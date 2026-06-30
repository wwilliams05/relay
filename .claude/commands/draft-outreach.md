# /draft-outreach — generate drafts for checked contacts (N5)

Read `src/relay/outreach.py` — the rules there are HARD constraints. Read them in full
before writing anything.

**Do:**
1. Read the Contacts tab; take only rows where `want_to_message` is checked.
2. For each, if `why == referral` and `referral_cleared` is false, SKIP and flag it —
   do not name an uncleared referrer.
3. Generate a short draft using `relay.outreach.draft_prompt(...)`. Open with the
   recipient-specific hook. Keep it brief. Barebones, in his voice — something to edit,
   not a finished product.
4. Create it as a Gmail DRAFT (`relay.gmail.create_draft`). Never send. Set `draft_created`.

**Self-check before each draft (per §6):** individual hook, not company enthusiasm ·
short · no referral ask on first contact · no Boeing/aerospace background · no GPA ·
no banned "no agenda" line · anchored to business-operations process improvement.

**Gate:** the user edits and sends every draft themselves.
