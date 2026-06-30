"""The outreach playbook, encoded once and reused by the draft + project skills.

These are HARD constraints. The draft-outreach skill (.claude/commands/draft-outreach.md)
references this spec; keeping it in code means the rules live in exactly one place.
"""

OUTREACH_RULES = """\
HARD RULES for every outreach draft:

1. Lead with a genuine, individual-specific hook — shared alma mater, a specific career
   transition, a public post, a role they moved into. NEVER open with broad enthusiasm
   for the company.
2. Short wins. Shorter consistently outperforms longer. Default to brief.
3. Barebones and in his voice — a draft to EDIT, not a polished final. Keep conversational
   honesty; do not over-polish.
4. No referral asks on first contact. Build the relationship; a thank-you beats an ask.
   Referencing something the contact OFFERED first (e.g. an intern opening) is fine;
   unsolicited asks are not.
5. Reserve the aerospace / Boeing family background for live conversations — never in a
   cold email.
6. No GPA in casual coffee-chat emails.
7. Verify before referencing — only use a contact's name as a referral once cleared;
   verify any specific claim (an article, a course) before it goes in.
8. Anchor to "business operations process improvement" so multi-track outreach reads as
   one coherent story.
9. BANNED LINE: never write "No agenda beyond hearing your perspective" or anything
   similar — reads as filler and slightly suspicious.
"""


def draft_prompt(contact_summary: str, profile_summary: str) -> str:
    """Compose the prompt used to generate a single outreach draft (N5)."""
    return (
        f"{OUTREACH_RULES}\n\n"
        f"ABOUT THE SENDER:\n{profile_summary}\n\n"
        f"ABOUT THE RECIPIENT:\n{contact_summary}\n\n"
        "Write a short cold email. Open with the recipient-specific hook. "
        "Output only the draft body — no subject line commentary, no explanation."
    )
