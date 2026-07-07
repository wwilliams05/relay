"""LocalXlsxTracker round-trips: upserts, human-gate preservation, sort + pruning."""

from __future__ import annotations

import zipfile
from datetime import date

from conftest import check_box as _check_box

from relay import config
from relay.models import Contact, EmailStatus, Job, Why
from relay.sheets import LocalXlsxTracker, contact_key, job_key


def _contact(**overrides) -> Contact:
    base = dict(
        name="Elan Reyes", title="Business Operations Analyst, Starlink", company="SpaceX",
        profile_url="https://www.linkedin.com/in/elan-reyes-example", why=Why.ALUMNI,
        school_match="University of Southern California", email="elan.reyes@spacex.com",
        email_status=EmailStatus.VERIFIED, hook="USC grad who moved from consulting into Starlink ops",
    )
    base.update(overrides)
    return Contact(**base)


def _job(**overrides) -> Job:
    base = dict(
        company="Stripe", title="Product Management Intern", location="San Francisco, CA",
        source="greenhouse", job_url="https://boards.example/stripe/pm-intern",
        date_posted=date(2026, 6, 5), fit_score=80, fit_reason="matches your target role",
    )
    base.update(overrides)
    return Job(**base)


# --- identity keys ---------------------------------------------------------------
def test_job_key_prefers_url() -> None:
    assert job_key(_job()) == "url::https://boards.example/stripe/pm-intern"
    assert job_key(_job(job_url=None)) == "ct::stripe::product management intern"


def test_contact_key_prefers_email() -> None:
    assert contact_key(_contact()) == "email::elan.reyes@spacex.com"
    assert contact_key(_contact(email=None)) == "nc::elan reyes::spacex"


# --- contacts ---------------------------------------------------------------------
def test_contacts_round_trip(tracker: LocalXlsxTracker) -> None:
    original = _contact(
        want_to_message=True, referral_cleared=False, draft_created=True,
        messaged_date=date(2026, 7, 1), responded=True,
        chat_notes="Talked Starlink ops tooling", next_step="Send thank-you note",
    )
    tracker.write_contacts([original])
    (read,) = tracker.read_contacts()
    assert read == original


def test_write_contacts_preserves_human_columns_on_rerun(tracker: LocalXlsxTracker) -> None:
    tracker.write_contacts([_contact()])
    _check_box(tracker.path, "Contacts", "name", "Elan Reyes", "want_to_message")

    # Re-discovery returns the same person (fresher machine data) + a new one.
    tracker.write_contacts([_contact(title="Senior BizOps Analyst"), _contact(
        name="Dana Okoro", email="dana.okoro@spacex.com", why=Why.SIMILAR_ROLE,
        school_match=None)])
    by_name = {c.name: c for c in tracker.read_contacts()}
    assert by_name["Elan Reyes"].want_to_message is True  # human tick survived
    assert by_name["Elan Reyes"].title == "Senior BizOps Analyst"  # machine data refreshed
    assert by_name["Dana Okoro"].want_to_message is False


def test_update_contact_overwrites_single_row(tracker: LocalXlsxTracker) -> None:
    tracker.write_contacts([_contact(), _contact(name="Dana Okoro", email="dana.okoro@spacex.com")])
    changed = _contact(draft_created=True, messaged_date=date(2026, 7, 2))
    tracker.update_contact(changed)
    by_name = {c.name: c for c in tracker.read_contacts()}
    assert by_name["Elan Reyes"].draft_created is True
    assert by_name["Elan Reyes"].messaged_date == date(2026, 7, 2)
    assert len(by_name) == 2


# --- jobs ---------------------------------------------------------------------------
def test_write_jobs_sorts_highest_fit_first(tracker: LocalXlsxTracker) -> None:
    tracker.write_jobs([
        _job(job_url="https://x.example/a", fit_score=30),
        _job(job_url="https://x.example/b", fit_score=90),
        _job(job_url="https://x.example/c", fit_score=50),
    ])
    assert [j.fit_score for j in tracker.read_jobs()] == [90, 50, 30]


def test_write_jobs_prunes_below_floor_unless_pursued(tracker: LocalXlsxTracker) -> None:
    tracker.write_jobs([
        _job(job_url="https://x.example/keep", fit_score=55),
        _job(job_url="https://x.example/noise", fit_score=5),   # below the 20 floor
    ])
    assert [j.fit_score for j in tracker.read_jobs()] == [55]

    # A pursued job survives even when its score sits under the floor.
    tracker.write_jobs([_job(job_url="https://x.example/low", fit_score=10, pursue=True)])
    urls = {j.job_url for j in tracker.read_jobs()}
    assert "https://x.example/low" in urls


def test_write_jobs_preserves_pursue_and_refreshes_score(tracker: LocalXlsxTracker) -> None:
    tracker.write_jobs([_job(fit_score=50)])
    _check_box(tracker.path, "Jobs", "title", "Product Management Intern", "pursue")

    tracker.write_jobs([_job(fit_score=60)])  # re-run rescored the same URL
    (read,) = tracker.read_jobs()
    assert read.pursue is True
    assert read.fit_score == 60


def test_jobs_round_trip_fields(tracker: LocalXlsxTracker) -> None:
    original = _job(pursue=True, status="applied")
    tracker.write_jobs([original])
    (read,) = tracker.read_jobs()
    assert read == original


def test_write_jobs_real_postings_evict_sample_rows(tracker: LocalXlsxTracker) -> None:
    """Fixture/demo rows (even old unlabeled ones with example.com URLs, even pursued)
    are purged the moment a real posting arrives — fake jobs must not linger."""
    tracker.write_jobs([
        _job(job_url="https://example.com/jobs/spacex-bizops-coop", source="linkedin",
             fit_score=90, pursue=True),  # the pre-label leak shape
        _job(company="Ramp", title="BizOps Intern", job_url="https://f.example/x",
             source="fixture", fit_score=80),
    ])
    assert len(tracker.read_jobs()) == 2  # all-sample batch: demo mode keeps them

    tracker.write_jobs([_job(job_url="https://boards.real/pm", source="greenhouse",
                             fit_score=60)])
    (kept,) = tracker.read_jobs()
    assert kept.job_url == "https://boards.real/pm"


def test_fixture_demo_rows_survive_fixture_reruns(tracker: LocalXlsxTracker) -> None:
    sample = _job(job_url="https://example.com/jobs/demo", source="fixture", fit_score=70)
    tracker.write_jobs([sample])
    tracker.write_jobs([sample])  # re-running the offline demo doesn't self-destruct
    assert len(tracker.read_jobs()) == 1


# --- checkbox injection ----------------------------------------------------------------
def test_checkbox_injection_round_trip(monkeypatch, tracker: LocalXlsxTracker) -> None:
    monkeypatch.setenv("RELAY_XLSX_CHECKBOXES", "1")
    tracker.write_jobs([_job()])
    with zipfile.ZipFile(tracker.path) as z:
        assert "xl/featurePropertyBag/featurePropertyBag.xml" in z.namelist()
    # The injected workbook still reads back cleanly.
    (read,) = tracker.read_jobs()
    assert read.company == "Stripe"
    assert read.pursue is False
    assert config.xlsx_checkboxes() is True
