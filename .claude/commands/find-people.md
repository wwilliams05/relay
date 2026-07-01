# /find-people — discover + enrich contacts (N2–N4)

You are running the people-discovery stage of Relay. Read `docs/PRD.md` §3, §5 first.

**Input:** a target company + role (ask if not given). Load the user's `Profile` via
`relay.resume.load_profile()` (run `/… profile` or `relay profile <pdf>` first if missing).

**Do:**
1. Derive `similar_titles` for the role — start from `relay.pipeline.default_similar_titles(role)`
   and refine (e.g. Business Operations Co-Op → "Business Operations", "BizOps",
   "Strategy & Operations", "Supply Chain", "Product Growth"). Set them on the `Target`.
2. Run the deterministic spine: `relay.pipeline.find_people(target, profile)` — this calls
   `apollo.search_people` + `apollo.enrich` and ranks by §5. Mind the credit budget (PRD §9);
   pass `enrich=False` to skip enrichment while iterating. Mutual-connection detection is
   intentionally out of scope (PRD §7).
3. For each contact, write a one-line, individual-specific `hook` per §6 (alumni / specific
   role transition / a public detail — NEVER generic company enthusiasm). `find_people` leaves
   `hook` unset on purpose; this is your job.
4. Persist: `tracker = relay.sheets.get_tracker()`, then `tracker.upsert_target(target)` and
   `tracker.write_contacts(contacts)`. `want_to_message` stays unchecked. Re-running is safe —
   `write_contacts` upserts and preserves the human-owned columns.
5. Print the `relay.pipeline.mutuals_nudge(contacts)` list as a manual "check LinkedIn for
   mutual connections" step.

**Gate:** stop here. The user checks `want_to_message` themselves before any drafting.
