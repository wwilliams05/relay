"""Job adapter plumbing (relay.jobs): title gate, date parsing, normalization."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from relay import jobs
from relay.jobs import _INTERN_TITLE_RE, _normalize, _strip_html, _to_date, _workday_posted_date


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


# --- fixture scrape ------------------------------------------------------------------
def test_scrape_fixture_mode_is_offline_and_bounded(monkeypatch) -> None:
    monkeypatch.setenv("RELAY_JOBS_RESULTS", "3")
    out = jobs.scrape(["business operations intern"])
    assert len(out) == 3
    assert all(j.company and j.title for j in out)
