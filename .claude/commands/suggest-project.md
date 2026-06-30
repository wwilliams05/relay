# /suggest-project — portfolio projects for a contact (N7)

**Input:** a target company and (optionally) a specific contact.

**Do:**
1. Suggest 2–3 concrete projects that would land in a coffee chat or as a portfolio
   attachment — tied to the company's actual domain and a skill worth showing
   (e.g. a SQL project on Starlink ops metrics to show a BizOps contact).
2. Each: one-line idea + `skills_shown`. Write to the **Projects** tab, `interested` unchecked.
3. When the user checks one, generate a `prd_prompt` — a tight, self-contained PRD prompt
   they can paste into an LLM to start vibe-coding. Scope it to a weekend build.

**Gate:** the user picks which project to build.
