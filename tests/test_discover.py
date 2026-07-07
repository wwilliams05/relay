"""Fit-scoring + ranking (relay.discover): the transparent rubric N-1 depends on."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from relay import discover
from relay.discover import (_is_us_location, _location_fit, derive_search_terms,
                            run_discovery, score_job)
from relay.models import Job, Profile


def _job(**overrides) -> Job:
    base = dict(
        company="Acme", title="Business Operations Intern", location=None,
        job_type="internship", source="test", job_url=None, date_posted=None,
    )
    base.update(overrides)
    return Job(**base)


# --- search terms -------------------------------------------------------------
def test_derive_search_terms_reads_typed_preferences(profile: Profile) -> None:
    terms = derive_search_terms(profile)
    assert terms == ["product manager intern", "business operations intern"]


def test_derive_search_terms_falls_back_to_resume_roles() -> None:
    p = Profile(name="x", roles=["Business Analyst"])
    assert derive_search_terms(p) == ["Business Analyst intern"]


def test_derive_search_terms_default_anchor() -> None:
    assert derive_search_terms(Profile(name="x")) == ["business operations intern"]


# --- role / major weighting ----------------------------------------------------
def test_target_role_outranks_generic_business_outranks_offtarget(profile: Profile) -> None:
    pm, _ = score_job(_job(title="Product Management Intern, Fall 2026"), profile)
    marketing, _ = score_job(_job(title="Marketing Intern"), profile)
    swe, _ = score_job(_job(title="Software Engineer Intern"), profile)
    assert pm > marketing > swe


def test_typed_preference_and_major_stack(profile: Profile) -> None:
    # 50 base + 30 preference hit + 12 business-major reinforcement.
    score, reason = score_job(_job(title="Product Management Intern"), profile)
    assert score == 92
    assert "matches your target role" in reason
    assert "fits your major" in reason


def test_generic_business_role_gets_smaller_boost(profile: Profile) -> None:
    # 50 base + 12 business-title hit + 12 major.
    score, reason = score_job(_job(title="Marketing Intern"), profile)
    assert score == 74
    assert "business/ops role" in reason


def test_offtarget_engineering_role_sinks_below_floor(profile: Profile) -> None:
    score, reason = score_job(_job(title="Software Engineer Intern"), profile)
    assert "off-target field" in reason
    assert score == 0  # 50 - 45 - 8 clamps at 0
    assert score < 20  # under the default RELAY_JOBS_MIN_FIT floor


def test_preference_hit_disarms_offtarget_penalty(profile: Profile) -> None:
    # "Product Manager, Hardware Intern" hits both lists; the preference hit blocks
    # the -45 off-target penalty (only the major's -8 off-field discount remains).
    score, reason = score_job(_job(title="Product Manager, Hardware Intern"), profile)
    assert "matches your target role" in reason
    assert "off-target field" not in reason
    assert score == 72


def test_non_internship_penalty(profile: Profile) -> None:
    intern = _job(title="Business Operations Coordinator", job_type="internship")
    fulltime = _job(title="Business Operations Coordinator", job_type=None)
    assert score_job(intern, profile)[0] - score_job(fulltime, profile)[0] == 15


def test_skills_only_lift_on_target_roles(profile: Profile) -> None:
    base, _ = score_job(_job(title="Business Operations Intern"), profile)
    with_skill, _ = score_job(_job(title="Business Operations Intern - SQL"), profile)
    assert with_skill - base == 2
    swe, _ = score_job(_job(title="Software Engineer Intern - SQL"), profile)
    swe_plain, _ = score_job(_job(title="Software Engineer Intern"), profile)
    assert swe == swe_plain  # no skills boost for off-field roles


# --- recency -------------------------------------------------------------------
def test_recency_weighting(profile: Profile) -> None:
    base = _job(title="Operations Intern")
    undated, _ = score_job(base, profile)
    today, _ = score_job(_job(title="Operations Intern", date_posted=date.today()), profile)
    this_month, _ = score_job(
        _job(title="Operations Intern", date_posted=date.today() - timedelta(days=20)), profile)
    stale, _ = score_job(
        _job(title="Operations Intern", date_posted=date.today() - timedelta(days=200)), profile)
    assert today - undated == 8
    assert this_month - undated == 4
    assert stale - undated == -6


# --- location ------------------------------------------------------------------
def test_location_weighting(profile: Profile) -> None:
    base = _job(title="Operations Intern")
    neutral, _ = score_job(base, profile)
    in_la, _ = score_job(_job(title="Operations Intern", location="Los Angeles, CA"), profile)
    elsewhere, _ = score_job(_job(title="Operations Intern", location="Austin, TX"), profile)
    vague, _ = score_job(_job(title="Operations Intern", location="United States"), profile)
    assert in_la - neutral == 12
    assert elsewhere - neutral == -20
    assert vague == neutral


def test_location_fit_aliases() -> None:
    prefs = ["New York", "Remote"]
    assert _location_fit(_job(location="Brooklyn, NY"), prefs) == (12, "in New York")
    assert _location_fit(_job(location="Remote - US"), prefs) == (12, "in Remote")
    assert _location_fit(_job(location="Austin, TX"), prefs)[0] == -20
    assert _location_fit(_job(location="Multiple Locations"), prefs) == (0, None)
    assert _location_fit(_job(location=None), prefs) == (0, None)
    assert _location_fit(_job(location="Austin, TX"), []) == (0, None)


# --- US-only gate ------------------------------------------------------------------
@pytest.mark.parametrize("loc,expected", [
    ("Austin, TX", True),
    ("CHARLOTTE, NC", True),
    ("US, CA, Santa Clara", True),
    ("New York New York United States", True),
    ("Seattle, Washington, USA", True),
    ("Warsaw, Poland", False),
    ("Sydney New South Wales Australia", False),
    ("London, United Kingdom", False),
    ("Hybrid - London", False),
    ("Mexico City, Mexico City, MEX", False),
    ("Bogota  Colombia", False),
    ("Bengaluru, India", False),
    ("Remote - EMEA", False),
    ("New York, NY / London", None),  # mixed signals -> keep
    ("3 Locations", None),
    ("Remote", None),
    ("", None),
    (None, None),
])
def test_is_us_location(loc, expected) -> None:
    assert _is_us_location(loc) is expected


def test_run_discovery_drops_non_us_by_default(profile: Profile, monkeypatch) -> None:
    scraped = [
        Job(company="Stripe", title="Business Operations Intern", location="Warsaw, Poland",
            job_url="https://x/warsaw", job_type="internship"),
        Job(company="Ramp", title="Business Operations Intern", location="Austin, TX",
            job_url="https://x/austin", job_type="internship"),
    ]
    monkeypatch.setattr(discover.jobs, "scrape", lambda terms: scraped)
    (kept,) = run_discovery(profile)
    assert kept.job_url == "https://x/austin"

    monkeypatch.setenv("RELAY_JOBS_US_ONLY", "0")  # international search opt-out
    assert len(run_discovery(profile)) == 2


# --- end-to-end fixture discovery ------------------------------------------------
def test_run_discovery_ranks_filters_and_floors(profile: Profile) -> None:
    jobs = run_discovery(profile)
    assert jobs, "fixture discovery returned nothing"
    titles = [j.title for j in jobs]
    # The full-time fixture row is dropped by the internship gate.
    assert not any("Marketing Coordinator" in t for t in titles)
    # Ranked best-first and everything clears the fit floor.
    scores = [j.fit_score for j in jobs]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= 20 for s in scores)
    assert all(j.fit_reason for j in jobs)


def test_run_discovery_collapses_duplicate_role_location(profile: Profile, monkeypatch) -> None:
    dupes = [
        Job(company="Stripe", title="Product Management Intern", location="SF",
            job_url="https://a.example/1", job_type="internship"),
        Job(company="Stripe", title="Product Management Intern", location="SF",
            job_url="https://a.example/2", job_type="internship"),
    ]
    monkeypatch.setattr(discover.jobs, "scrape", lambda terms: dupes)
    out = run_discovery(profile)
    assert len(out) == 1
    assert "more location" not in (out[0].location or "")  # same city -> no note


def test_run_discovery_collapses_cross_city_siblings(profile: Profile, monkeypatch) -> None:
    """One req posted per city (the Greenhouse/Workday pattern) becomes one row: the
    best-scored city wins and the siblings fold into a '+N more' note."""
    cities = [
        Job(company="Stripe", title="Product Management Intern", location="Austin, TX",
            job_url="https://a.example/atx", job_type="internship"),
        Job(company="Stripe", title="Product Management Intern",
            location="Los Angeles, CA",  # preferred city -> highest fit -> keeper
            job_url="https://a.example/la", job_type="internship"),
        Job(company="Stripe", title="Product Management Intern", location="Denver, CO",
            job_url="https://a.example/den", job_type="internship"),
    ]
    monkeypatch.setattr(discover.jobs, "scrape", lambda terms: cities)
    (kept,) = run_discovery(profile)
    assert kept.job_url == "https://a.example/la"
    assert kept.location == "Los Angeles, CA (+2 more locations)"
