"""The outreach playbook, encoded once and reused by the draft + project skills.

These are HARD constraints. The draft-outreach skill (.claude/commands/draft-outreach.md)
references this spec; keeping it in code means the rules live in exactly one place.
"""

from __future__ import annotations

from .models import Contact, Profile, Why

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


# --- deterministic drafting + rule lint (N5) ----------------------------------
# The /draft-outreach skill writes richer drafts with the model in the loop;
# `build_draft` is the deterministic fallback the CLI/GUI use so N5 runs offline.
# Both paths are checked by `lint_draft`, which encodes the rules above as code.

# Content that must never appear in a cold email (§6). Checked case-insensitively.
_BANNED_SUBSTRINGS: tuple[tuple[str, str], ...] = (
    ("no agenda", 'banned "no agenda" line'),
    ("gpa", "mentions GPA"),
    ("boeing", "aerospace/Boeing background is for live conversations only"),
    ("aerospace", "aerospace/Boeing background is for live conversations only"),
)

# Referral *asks*. Referencing something the contact offered first is fine; asking
# on first contact is not — these phrases are asks.
_REFERRAL_ASKS: tuple[str, ...] = (
    "refer me", "could you refer", "would you refer", "can you refer",
    "willing to refer", "a referral", "your referral", "put in a good word",
    "pass along my resume", "forward my resume", "pass my resume",
    "submit my application", "flag my application",
)

# Company-enthusiasm openers — the opposite of an individual-specific hook.
_ENTHUSIASM_OPENERS: tuple[str, ...] = (
    "huge fan", "big fan of", "long-time fan", "always admired", "really admire",
    "so excited about", "passionate about", "dream company", "love what",
)

MAX_DRAFT_WORDS = 120  # "short wins" — anything longer needs a human rewrite anyway


def lint_draft(text: str, first_contact: bool = True) -> list[str]:
    """Check a draft (subject + body) against the rules. Returns violations; [] = clean."""
    low = text.lower()
    violations = [why for needle, why in _BANNED_SUBSTRINGS if needle in low]
    if first_contact:
        violations.extend(
            f"referral ask on first contact ({ask!r})" for ask in _REFERRAL_ASKS if ask in low
        )
    opener = low[:160]
    violations.extend(
        f"opens with company enthusiasm, not an individual hook ({phrase!r})"
        for phrase in _ENTHUSIASM_OPENERS if phrase in opener
    )
    words = len(text.split())
    if words > MAX_DRAFT_WORDS:
        violations.append(f"too long ({words} words; keep it under {MAX_DRAFT_WORDS})")
    return violations


# Long school names read better shortened the way people actually say them.
_SCHOOL_SHORT = {
    "university of southern california": "USC",
    "washington university in st. louis": "WashU",
    "washington university": "WashU",
}


def _short_school(school: str) -> str:
    return _SCHOOL_SHORT.get(school.strip().lower(), school.strip())


def _first_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[0] if parts else "there"


def _opening(contact: Contact, school: str | None) -> str:
    """The individual-specific hook line. A skill/human-written `hook` wins; otherwise
    build one from the structured facts we actually have (school, title, company)."""
    if contact.hook:
        line = contact.hook.strip()
        return line if line[-1:] in ".!?" else line + "."
    role = f"{contact.title} at {contact.company}" if contact.title else f"at {contact.company}"
    if school:
        return (f"I'm a {school} student, and I saw you went from {school} to "
                f"{role} — that's a path I'd love to hear about.")
    return (f"I came across your profile while reading up on how {contact.company} "
            f"runs business operations, and your role ({contact.title or 'ops'}) is "
            "the kind of work I'm trying to learn from.")


def build_draft(profile: Profile, contact: Contact) -> tuple[str, str]:
    """Deterministic, rule-abiding (subject, body) for one checked contact.

    Barebones on purpose — a starting point the user edits, not a finished email.
    Raises ValueError on an uncleared referral (never name an uncleared referrer)
    or if the assembled draft somehow violates the rules above.
    """
    if contact.why == Why.REFERRAL and not contact.referral_cleared:
        raise ValueError(
            f"{contact.name} is an uncleared referral — clear `referral_cleared` "
            "in the tracker before drafting (never name an uncleared referrer)."
        )

    school = _short_school(contact.school_match) if contact.school_match else None
    first = _first_name(contact.name)
    sender = _first_name(profile.name)

    if contact.why == Why.REFERRAL:  # cleared: referencing what they offered is fine
        opening = ("Thanks again for offering to point me toward the opening on your "
                   "team — I wanted to follow up while it's fresh.")
        subject = "Following up on the opening you mentioned"
    else:
        opening = _opening(contact, school)
        subject = (f"{school} student with a quick question" if school
                   else f"Quick question about your work at {contact.company}")

    anchor = (f"Most of what I've done so far centers on {profile.anchor_framing}, "
              "and I'm trying to figure out how that translates into work like yours.")
    ask = ("Would you be open to a quick 15-minute chat in the next couple of weeks? "
           "No pressure at all if you're slammed.")
    body = f"Hi {first},\n\n{opening} {anchor}\n\n{ask}\n\nThanks,\n{sender}\n"

    violations = lint_draft(f"{subject}\n{body}")
    if violations:  # e.g. a human-written hook that smuggles in banned content
        raise ValueError(f"draft for {contact.name} breaks the outreach rules: "
                         + "; ".join(violations))
    return subject, body
