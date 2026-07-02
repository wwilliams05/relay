"""N5 end-to-end in fixture mode: gmail .eml drafts + the human-gated flow logic."""

from __future__ import annotations

from email import message_from_bytes
from pathlib import Path

import pytest

from relay import config, flow, gmail
from relay.models import Contact, EmailStatus, Profile, Why


def _contact(name: str, **overrides) -> Contact:
    first = name.split()[0].lower()
    base = dict(
        name=name, title="Business Operations Analyst", company="SpaceX",
        why=Why.SIMILAR_ROLE, email=f"{first}@spacex.com",
        email_status=EmailStatus.VERIFIED, want_to_message=True,
    )
    base.update(overrides)
    return Contact(**base)


# --- gmail fixture adapter ------------------------------------------------------
def test_fixture_create_draft_writes_eml(hermetic_env: Path, profile: Profile) -> None:
    ref = gmail.create_draft(_contact("Elan Reyes"), "Quick question", "Hi Elan,\n\nShort.\n")
    path = Path(ref)
    assert path.exists()
    assert path.parent == config.drafts_dir()
    msg = message_from_bytes(path.read_bytes())
    assert msg["To"] == "elan@spacex.com"
    assert msg["Subject"] == "Quick question"
    assert msg["X-Relay"] == "draft only; Relay never sends"
    assert "Hi Elan," in msg.get_payload()


def test_create_draft_requires_email(profile: Profile) -> None:
    with pytest.raises(ValueError, match="no email"):
        gmail.create_draft(_contact("Elan Reyes", email=None), "s", "b")


def test_gmail_never_sends() -> None:
    """Golden rule: the adapter has no code path that calls a send endpoint.

    AST-based so docstrings/comments may *mention* sending (to forbid it) while any
    actual `<x>.send(...)` attribute access in code fails the build.
    """
    import ast

    tree = ast.parse(Path(gmail.__file__).read_text(encoding="utf-8"))
    sends = [n for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and n.attr in {"send", "send_message"}]
    assert not sends


# --- the N5 flow -------------------------------------------------------------------
def _seed(tracker) -> None:
    tracker.write_contacts([
        _contact("Elan Reyes", why=Why.ALUMNI,
                 school_match="University of Southern California"),
        _contact("Rhea Vault", why=Why.REFERRAL, referral_cleared=False),
        _contact("Casey Quiet", want_to_message=False),
        _contact("Noah Noemail", email=None, email_status=EmailStatus.UNAVAILABLE),
        _contact("Ana Cleared", why=Why.REFERRAL, referral_cleared=True),
    ])


def test_draft_outreach_gates_and_flags(tracker, profile: Profile) -> None:
    _seed(tracker)
    run = flow.draft_outreach(profile)

    assert sorted(c.name for c, _ in run.created) == ["Ana Cleared", "Elan Reyes"]
    assert [c.name for c in run.skipped_referrals] == ["Rhea Vault"]
    assert [c.name for c in run.skipped_no_email] == ["Noah Noemail"]
    assert run.already_drafted == 0 and not run.rule_violations

    # Only the two safe contacts got a draft file; the uncleared referral never did.
    files = sorted(p.name for p in config.drafts_dir().glob("*.eml"))
    assert files == ["spacex-ana-cleared.eml", "spacex-elan-reyes.eml"]

    by_name = {c.name: c for c in tracker.read_contacts()}
    assert by_name["Elan Reyes"].draft_created is True
    assert by_name["Ana Cleared"].draft_created is True
    assert by_name["Rhea Vault"].draft_created is False  # flagged, never drafted
    assert by_name["Casey Quiet"].draft_created is False  # unchecked -> untouched
    assert by_name["Noah Noemail"].draft_created is False


def test_draft_outreach_rerun_is_idempotent(tracker, profile: Profile) -> None:
    _seed(tracker)
    flow.draft_outreach(profile)
    rerun = flow.draft_outreach(profile)
    assert not rerun.created
    assert rerun.already_drafted == 2
    assert [c.name for c in rerun.skipped_referrals] == ["Rhea Vault"]  # still flagged
    assert len(list(config.drafts_dir().glob("*.eml"))) == 2


def test_draft_outreach_quarantines_rule_breaking_hooks(tracker, profile: Profile) -> None:
    tracker.write_contacts([
        _contact("Bad Hook", hook="We're both aerospace people at heart")])
    run = flow.draft_outreach(profile)
    assert not run.created
    assert [c.name for c, _ in run.rule_violations] == ["Bad Hook"]
    assert not list(config.drafts_dir().glob("*.eml"))
    assert {c.name: c for c in tracker.read_contacts()}["Bad Hook"].draft_created is False


def test_draft_outreach_reports_nothing_checked(tracker, profile: Profile) -> None:
    tracker.write_contacts([_contact("Casey Quiet", want_to_message=False)])
    assert flow.draft_outreach(profile).nothing_checked is True
