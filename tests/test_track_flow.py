"""N6 (log-chat) + N7 (project suggester) flows against the fixture tracker."""

from __future__ import annotations

from datetime import date

import pytest

from relay import flow
from relay.models import Contact, Job, Profile, Project, Why


def _seed_contacts(tracker) -> None:
    tracker.write_contacts([
        Contact(name="Elan Reyes", company="SpaceX", why=Why.ALUMNI,
                email="elan.reyes@spacex.com"),
        Contact(name="Dana Okoro", company="SpaceX", why=Why.SIMILAR_ROLE,
                email="dana.okoro@spacex.com"),
        Contact(name="Dana Brooks", company="Ramp", why=Why.SIMILAR_ROLE,
                email="dana.brooks@ramp.com"),
    ])


# --- N6: log-chat ---------------------------------------------------------------
def test_log_chat_updates_only_given_fields(tracker) -> None:
    _seed_contacts(tracker)
    updated = flow.log_chat(
        "elan reyes", responded=True, notes="Talked Starlink ops tooling",
        next_step="Send thank-you note", messaged_date=date(2026, 7, 1))
    assert updated.responded is True
    assert updated.chat_notes == "Talked Starlink ops tooling"

    stored = {c.name: c for c in tracker.read_contacts()}["Elan Reyes"]
    assert stored.responded is True
    assert stored.messaged_date == date(2026, 7, 1)
    assert stored.next_step == "Send thank-you note"
    # Untouched fields survive.
    assert stored.email == "elan.reyes@spacex.com"
    assert stored.why == Why.ALUMNI


def test_log_chat_appends_notes_across_chats(tracker) -> None:
    _seed_contacts(tracker)
    flow.log_chat("Elan", notes="First chat: ops tooling")
    updated = flow.log_chat("Elan", notes="Second chat: offered async Q&A")
    assert updated.chat_notes == "First chat: ops tooling | Second chat: offered async Q&A"


def test_log_chat_partial_name_resolves_when_unique(tracker) -> None:
    _seed_contacts(tracker)
    assert flow.log_chat("okoro", responded=False).name == "Dana Okoro"


def test_log_chat_rejects_unknown_and_ambiguous_names(tracker) -> None:
    _seed_contacts(tracker)
    with pytest.raises(RuntimeError, match="no contact matching"):
        flow.log_chat("Nobody Here", responded=True)
    with pytest.raises(RuntimeError, match="ambiguous"):
        flow.log_chat("Dana", responded=True)


# --- N7: projects ------------------------------------------------------------------
def _projects() -> list[Project]:
    return [
        Project(target_company="SpaceX", for_contact="Elan Reyes",
                project_idea="SQL dashboard on synthetic Starlink ops metrics",
                skills_shown=["SQL", "data modeling"]),
        Project(target_company="Ramp",
                project_idea="Spend-approval workflow process map",
                skills_shown=["process improvement"]),
    ]


def test_add_projects_upserts_without_duplicating(tracker) -> None:
    assert flow.add_projects(_projects()) == 2
    assert flow.add_projects(_projects()) == 2  # re-suggest the same ideas
    assert len(tracker.read_projects()) == 2


# --- funnel status --------------------------------------------------------------
def test_status_walks_the_gates(tracker) -> None:
    # Empty tracker: the front door is job discovery.
    assert "relay discover" in flow.status_summary().next_step

    # Jobs found but none pursued.
    tracker.write_jobs([Job(company="Stripe", title="PM Intern",
                            job_url="https://x/1", fit_score=80)])
    s = flow.status_summary()
    assert (s.jobs_total, s.jobs_pursued, s.top_fit) == (1, 0, 80)
    assert "pursue" in s.next_step

    # Pursued, contacts found, one checked but not drafted -> draft is next.
    from conftest import check_box
    check_box(tracker.path, "Jobs", "company", "Stripe", "pursue")
    _seed_contacts(tracker)
    check_box(tracker.path, "Contacts", "name", "Elan Reyes", "want_to_message")
    s = flow.status_summary()
    assert (s.contacts_total, s.contacts_checked, s.drafts_created) == (3, 1, 0)
    assert "relay draft" in s.next_step


def test_status_after_drafting_points_at_gmail(tracker, profile: Profile) -> None:
    from conftest import check_box
    tracker.write_jobs([Job(company="SpaceX", title="Ops Intern",
                            job_url="https://x/1", fit_score=80, pursue=True)])
    _seed_contacts(tracker)
    check_box(tracker.path, "Contacts", "name", "Elan Reyes", "want_to_message")
    flow.draft_outreach(profile)
    s = flow.status_summary()
    assert s.drafts_created == 1
    assert "send your drafts" in s.next_step


def test_fill_prd_prompts_only_for_interested(tracker, profile: Profile) -> None:
    flow.add_projects(_projects())
    assert flow.fill_prd_prompts(profile) == []  # nothing ticked yet

    # The human ticks `interested` in the workbook itself (write_projects would
    # deliberately keep the stored value, so a programmatic tick can't leak in).
    from conftest import check_box
    check_box(tracker.path, "Projects", "target_company", "SpaceX", "interested")

    filled = flow.fill_prd_prompts(profile)
    assert [p.target_company for p in filled] == ["SpaceX"]
    prompt = filled[0].prd_prompt
    assert "SQL dashboard on synthetic Starlink ops metrics" in prompt
    assert "Elan Reyes at SpaceX" in prompt
    assert "SQL, data modeling" in prompt
    assert "business operations process improvement" in prompt  # the anchor
    assert "ONE weekend" in prompt

    stored = {p.target_company: p for p in tracker.read_projects()}
    assert stored["SpaceX"].prd_prompt == prompt  # persisted
    assert stored["SpaceX"].interested is True  # tick survived the rewrite
    assert stored["Ramp"].prd_prompt is None  # unticked -> untouched

    assert flow.fill_prd_prompts(profile) == []  # idempotent: already filled
