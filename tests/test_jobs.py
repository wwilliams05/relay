"""Job adapter plumbing (relay.jobs): title gate, date parsing, normalization."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from relay import jobs
from relay.jobs import (_INTERN_TITLE_RE, _normalize, _strip_html, _to_date,
                        _workday_location, _workday_posted_date)


# --- intern title gate ----------------------------------------------------------
@pytest.mark.parametrize("title", [
    "Software Engineering Intern",
    "Business Operations Internship",
    "Fall 2026 Co-op - BizOps",
    "Co-Op, Supply Chain",
    "Coop Student",
    "Summer Analyst Program 2026",
    "2026 Summer Associate",
    "Product Interns",
])
def test_intern_title_gate_matches(title: str) -> None:
    assert _INTERN_TITLE_RE.search(title)


@pytest.mark.parametrize("title", [
    "Internal Audit Manager",
    "International Sales Lead",
    "Internet Infrastructure Engineer",
    "Senior Product Manager",
])
def test_intern_title_gate_rejects_lookalikes(title: str) -> None:
    assert not _INTERN_TITLE_RE.search(title)


# --- date coercion ----------------------------------------------------------------
def test_to_date_passthrough_and_iso() -> None:
    d = date(2026, 6, 1)
    assert _to_date(d) == d
    assert _to_date(datetime(2026, 6, 1, 12, 30)) == d
    assert _to_date("2026-06-01") == d
    assert _to_date("2026-06-01T12:00:00Z") == d


def test_to_date_lever_epoch_millis() -> None:
    ms = 1750000000000  # Lever posts epoch-milliseconds
    expected = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()
    assert _to_date(ms) == expected
    assert _to_date(str(ms)) == expected


def test_to_date_amazon_month_name_format() -> None:
    assert _to_date("September 24, 2025") == date(2025, 9, 24)


@pytest.mark.parametrize("bad", [None, "", "garbage", "junk-date"])
def test_to_date_garbage_is_none(bad) -> None:
    assert _to_date(bad) is None


# --- workday "Posted N Days Ago" ---------------------------------------------------
@pytest.mark.parametrize("text,days", [
    ("Posted Today", 0),
    ("Posted Yesterday", 1),
    ("Posted 5 Days Ago", 5),
    ("Posted 30+ Days Ago", 30),
    ("Posted 2 Weeks Ago", 14),
    ("Posted 3 Months Ago", 90),
])
def test_workday_posted_date(text: str, days: int) -> None:
    assert _workday_posted_date(text) == date.today() - timedelta(days=days)


@pytest.mark.parametrize("bad", [None, "", "Recently posted"])
def test_workday_posted_date_unparseable(bad) -> None:
    assert _workday_posted_date(bad) is None


@pytest.mark.parametrize("raw,expected", [
    ("Locations: New York, NY; Austin, TX", "New York, NY / Austin, TX"),
    ("Location: McLean, Virginia", "McLean, Virginia"),
    ("San Francisco, CA • Seattle, WA", "San Francisco, CA / Seattle, WA"),
    ("3 Locations", "3 Locations"),
    (None, None),
    ("", None),
])
def test_workday_location_tidy(raw, expected) -> None:
    assert _workday_location(raw) == expected


# --- normalization -----------------------------------------------------------------
def test_normalize_defaults_and_trims() -> None:
    job = _normalize({"company": "  Stripe ", "title": " PM Intern ", "site": "greenhouse",
                      "location": " SF ", "job_url": " https://x.example/1 "})
    assert (job.company, job.title, job.source) == ("Stripe", "PM Intern", "greenhouse")
    assert job.location == "SF"
    assert job.job_url == "https://x.example/1"
    empty = _normalize({})
    assert (empty.company, empty.title) == ("(unknown)", "(untitled)")
    assert empty.location is None and empty.job_url is None


def test_strip_html() -> None:
    assert _strip_html("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"
    assert _strip_html("") is None
    assert _strip_html(None) is None


def test_amazon_rows_normalize(monkeypatch) -> None:
    record = {
        "title": "Business Analyst Intern",
        "normalized_location": "Seattle, Washington, USA",
        "job_path": "/en/jobs/3091886/business-analyst-intern",
        "posted_date": "September 24, 2025",
        "description": "<p>Ops internship</p>",
    }
    monkeypatch.setattr(jobs, "_ats_get", lambda url: {"jobs": [record]})
    (row,) = jobs._amazon_rows({"company": "Amazon", "provider": "amazon"})
    assert row["job_url"] == "https://www.amazon.jobs/en/jobs/3091886/business-analyst-intern"
    assert row["location"] == "Seattle, Washington, USA"
    assert row["site"] == "amazon"
    job = jobs._normalize(row)
    assert job.date_posted == date(2025, 9, 24)
    assert job.description == "Ops internship"


def test_company_domain_reads_targets_yml() -> None:
    assert jobs.company_domain("SpaceX") == "spacex.com"
    assert jobs.company_domain("spacex") == "spacex.com"  # case-insensitive
    assert jobs.company_domain("Scale AI") == "scale.com"
    assert jobs.company_domain("Unknown Startup") is None


# --- fixture scrape ------------------------------------------------------------------
def test_scrape_fixture_mode_is_offline_and_bounded(monkeypatch) -> None:
    monkeypatch.setenv("RELAY_JOBS_RESULTS", "3")
    out = jobs.scrape(["business operations intern"])
    assert len(out) == 3
    assert all(j.company and j.title for j in out)
    # Demo rows are labeled so trackers can recognize (and later evict) them.
    assert all(j.source == "fixture" for j in out)


def test_auto_mode_never_serves_fixtures(monkeypatch) -> None:
    """A transient network failure must return empty, not seed fake postings."""
    monkeypatch.setenv("RELAY_JOBS_MODE", "auto")
    monkeypatch.setattr(jobs, "_ats_scrape", lambda *a: [])

    def no_network(*a):
        raise RuntimeError("boards unreachable")

    monkeypatch.setattr(jobs, "_live_scrape", no_network)
    assert jobs.scrape(["business operations intern"]) == []
