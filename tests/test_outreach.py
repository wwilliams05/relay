"""Outreach voice rules as code: lint_draft + the deterministic build_draft (§6)."""

from __future__ import annotations

import pytest

from relay.models import Contact, EmailStatus, Profile, Why
from relay.outreach import MAX_DRAFT_WORDS, build_draft, lint_draft


def _contact(**overrides) -> Contact:
    base = dict(
        name="Elan Reyes", title="Business Operations Analyst, Starlink", company="SpaceX",
        why=Why.ALUMNI, school_match="University of Southern California",
        email="elan.reyes@spacex.com", email_status=EmailStatus.VERIFIED,
        want_to_message=True,
    )
    base.update(overrides)
    return Contact(**base)


# --- lint --------------------------------------------------------------------
def test_lint_flags_banned_content() -> None:
    assert lint_draft("No agenda beyond hearing your perspective.")
    assert lint_draft("My GPA is 3.9.")
    assert lint_draft("I grew up around Boeing.")
    assert lint_draft("My family works in aerospace.")


def test_lint_flags_referral_asks_on_first_contact() -> None:
    assert lint_draft("Could you refer me for the role?")
    assert lint_draft("Would you put in a good word?")
    assert lint_draft("Happy to send a resume if you'd submit my application.")
    # ... but the same text is fine when it's not a first contact.
    assert lint_draft("Could you refer me for the role?", first_contact=False) == []


def test_lint_flags_company_enthusiasm_opener() -> None:
    assert lint_draft("Hi! I'm a huge fan of SpaceX and everything you do.")
    # Enthusiasm buried later isn't an *opener* problem; only the head is checked.
    long_tail = ("Hi Elan,\n\nI saw your move from consulting into Starlink ops. " +
                 "x " * 60 + "big fan of the team.")
    assert not any("enthusiasm" in v for v in lint_draft(long_tail))


def test_lint_flags_overlong_draft() -> None:
    assert any("too long" in v for v in lint_draft("word " * (MAX_DRAFT_WORDS + 1)))


def test_lint_clean_draft_passes() -> None:
    assert lint_draft(
        "Hi Elan,\n\nI'm a USC student and saw your path into Starlink ops. "
        "Would you be open to a quick 15-minute chat?\n\nThanks,\nWeston") == []


# --- build_draft ------------------------------------------------------------------
def test_build_draft_alumni(profile: Profile) -> None:
    subject, body = build_draft(profile, _contact())
    assert subject == "USC student with a quick question"
    assert body.startswith("Hi Elan,")
    assert "USC" in body  # the individual-specific hook, not company enthusiasm
    assert "business operations process improvement" in body  # the anchor (§6)
    assert body.rstrip().endswith("Weston")
    assert len(body.split()) <= MAX_DRAFT_WORDS
    assert lint_draft(f"{subject}\n{body}") == []


def test_build_draft_similar_role_without_school(profile: Profile) -> None:
    subject, body = build_draft(profile, _contact(
        name="Marcus Feld", why=Why.SIMILAR_ROLE, school_match=None,
        email="marcus.feld@spacex.com"))
    assert subject == "Quick question about your work at SpaceX"
    assert "SpaceX" in body
    assert lint_draft(f"{subject}\n{body}") == []


def test_build_draft_prefers_written_hook(profile: Profile) -> None:
    hook = "I saw your jump from strategy consulting straight into Starlink ops"
    _, body = build_draft(profile, _contact(hook=hook))
    assert f"{hook}." in body  # used verbatim, terminal punctuation added


def test_build_draft_refuses_uncleared_referral(profile: Profile) -> None:
    with pytest.raises(ValueError, match="uncleared referral"):
        build_draft(profile, _contact(why=Why.REFERRAL, referral_cleared=False))


def test_build_draft_cleared_referral_references_offer_without_asking(
        profile: Profile) -> None:
    subject, body = build_draft(profile, _contact(why=Why.REFERRAL, referral_cleared=True))
    assert "offering" in body  # references what *they* offered first
    assert "Following up" in subject
    assert lint_draft(f"{subject}\n{body}") == []


def test_build_draft_rejects_rule_breaking_hook(profile: Profile) -> None:
    with pytest.raises(ValueError, match="breaks the outreach rules"):
        build_draft(profile, _contact(hook="Fellow Boeing family kid turned ops nerd"))
