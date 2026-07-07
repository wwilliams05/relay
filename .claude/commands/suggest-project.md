# /suggest-project — portfolio projects for a contact (N7)

**Input:** a target company and (optionally) a specific contact.

**Do:**
1. Suggest 2–3 concrete projects that would land in a coffee chat or as a portfolio
   attachment — tied to the company's actual domain and a skill worth showing
   (e.g. a SQL project on Starlink ops metrics to show a BizOps contact).
2. Each: one-line idea + `skills_shown`, as a `relay.models.Project`. Persist with
   `relay.flow.add_projects([...])` — it upserts, so re-suggesting never duplicates a
   row or unticks the user's `interested` box. Leave `interested` unchecked.
3. When the user checks one, generate its `prd_prompt` — a tight, self-contained PRD
   prompt they can paste into an LLM to start vibe-coding, scoped to a weekend build.
   `relay.flow.fill_prd_prompts(profile)` (or the `relay prd` CLI) does this
   deterministically from `relay.outreach.project_prd_prompt`; write a sharper one
   yourself when you have real context about the company, but keep the weekend scope.

**Gate:** the user picks which project to build.
