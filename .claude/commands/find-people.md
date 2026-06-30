# /find-people — discover + enrich contacts (N2–N4)

You are running the people-discovery stage of Relay. Read `docs/PRD.md` §3, §5 first.

**Input:** a target company + role (ask if not given). Load the user's `Profile`.

**Do:**
1. Derive `similar_titles` for the role (e.g. Business Operations Co-Op →
   "Business Operations", "BizOps", "Strategy & Operations", "Supply Chain", "Product Growth").
2. Call `relay.apollo.search_people(org, titles, schools=[user's schools])`.
3. Enrich the promising ones (`relay.apollo.enrich`) — mind credit budget (PRD §9).
4. Classify each `why` and write a one-line, individual-specific `hook` per §6
   (alumni / specific role transition / a public detail — NEVER generic company enthusiasm).
5. Rank by §5 priority. Write to the **Contacts** tab via the Tracker, `want_to_message`
   unchecked.
6. For the top contacts, print a manual "check LinkedIn for mutual connections" nudge.

**Gate:** stop here. The user checks `want_to_message` themselves before any drafting.
