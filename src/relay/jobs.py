"""Job-discovery adapter: scrape postings via JobSpy (N-1).

Two modes, selected by `RELAY_JOBS_MODE` (see config.jobs_mode):
- "live"    — scrape real boards (Indeed / LinkedIn / Glassdoor / ZipRecruiter /
              Google) via JobSpy. Network-bound; boards rate-limit, so results vary.
- "fixture" — canned internship/co-op postings so the launcher flow runs fully offline.
- "auto"    — try live, fall back to fixtures if scraping errors or returns nothing.

Every posting funnels through `_normalize` so live and fixture rows map to a Job the
same way. Fit-scoring against the Profile happens in `relay.discover`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import config
from .models import Job

_DEFAULT_SITES = ["indeed", "linkedin", "google", "zip_recruiter"]


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _normalize(row: dict[str, Any]) -> Job:
    return Job(
        company=str(row.get("company") or "").strip() or "(unknown)",
        title=str(row.get("title") or "").strip() or "(untitled)",
        location=(str(row.get("location")).strip() or None) if row.get("location") else None,
        job_type=(str(row.get("job_type")).strip() or None) if row.get("job_type") else None,
        source=(str(row.get("site") or row.get("source") or "").strip() or None),
        job_url=(str(row.get("job_url")).strip() or None) if row.get("job_url") else None,
        date_posted=_to_date(row.get("date_posted")),
        description=(str(row.get("description")).strip() or None) if row.get("description") else None,
    )


# --- live (JobSpy) -----------------------------------------------------------
def _live_scrape(terms: list[str], location: str, results_wanted: int) -> list[Job]:
    from jobspy import scrape_jobs  # imported lazily; heavy (pandas) dependency

    jobs: list[Job] = []
    per_term = max(1, results_wanted // max(1, len(terms)))
    for term in terms:
        df = scrape_jobs(
            site_name=_DEFAULT_SITES,
            search_term=term,
            location=location,
            results_wanted=per_term,
            hours_old=None,
            country_indeed="USA",
            description_format="markdown",
            verbose=0,
        )
        if df is None or df.empty:
            continue
        for record in df.to_dict("records"):
            jobs.append(_normalize(record))
    return jobs


# --- fixtures ----------------------------------------------------------------
# Canned Fall-2026-style PM / BizOps internships across companies, with descriptions
# that carry keywords for fit-scoring. Lets the whole launcher flow run with no network.
_FIXTURE_JOBS: list[dict[str, Any]] = [
    {
        "company": "SpaceX", "title": "Business Operations Co-Op (Starlink), Fall 2026",
        "location": "Redmond, WA", "job_type": "internship", "site": "linkedin",
        "job_url": "https://example.com/jobs/spacex-bizops-coop",
        "date_posted": "2026-06-01",
        "description": "Drive business operations and process improvement for Starlink. "
                       "SQL, analytics, supply chain, cross-functional ops. Co-op / internship.",
    },
    {
        "company": "Stripe", "title": "Product Management Intern, Fall 2026",
        "location": "San Francisco, CA", "job_type": "internship", "site": "indeed",
        "job_url": "https://example.com/jobs/stripe-pm-intern",
        "date_posted": "2026-06-05",
        "description": "Product management internship. Work with engineering on product "
                       "requirements, growth, and go-to-market. Analytics and SQL a plus.",
    },
    {
        "company": "Ramp", "title": "Business Operations & Strategy Intern",
        "location": "New York, NY", "job_type": "internship", "site": "linkedin",
        "job_url": "https://example.com/jobs/ramp-bizops-intern",
        "date_posted": "2026-05-28",
        "description": "BizOps and strategy internship. Process improvement, operations "
                       "analytics, and cross-functional projects. Fall 2026.",
    },
    {
        "company": "Notion", "title": "Associate Product Manager Intern",
        "location": "San Francisco, CA", "job_type": "internship", "site": "google",
        "job_url": "https://example.com/jobs/notion-apm-intern",
        "date_posted": "2026-06-10",
        "description": "APM internship building product features and growth experiments.",
    },
    {
        "company": "Anduril", "title": "Supply Chain Operations Co-Op, Fall 2026",
        "location": "Costa Mesa, CA", "job_type": "internship", "site": "indeed",
        "job_url": "https://example.com/jobs/anduril-supplychain-coop",
        "date_posted": "2026-06-03",
        "description": "Supply chain and business operations co-op. Process improvement, "
                       "procurement analytics, SQL. Business operations throughline.",
    },
    {
        "company": "DoorDash", "title": "Strategy & Operations Intern",
        "location": "Remote", "job_type": "internship", "site": "linkedin",
        "job_url": "https://example.com/jobs/doordash-stratops-intern",
        "date_posted": "2026-05-20",
        "description": "Strategy and operations internship. Analytics, experimentation, "
                       "and operational process improvement across marketplace teams.",
    },
    {
        "company": "Acme Corp", "title": "Marketing Coordinator (Full-time)",
        "location": "Austin, TX", "job_type": "fulltime", "site": "indeed",
        "job_url": "https://example.com/jobs/acme-marketing",
        "date_posted": "2026-04-15",
        "description": "Full-time marketing coordinator. Social media and events. "
                       "Not an internship.",
    },
]


def _fixture_scrape(terms: list[str], location: str, results_wanted: int) -> list[Job]:
    return [_normalize(row) for row in _FIXTURE_JOBS[:results_wanted]]


# --- public API --------------------------------------------------------------
def scrape(
    terms: list[str],
    location: str | None = None,
    results_wanted: int | None = None,
) -> list[Job]:
    """N-1: scrape postings for `terms`. Returns raw (unranked, un-deduped) Jobs.

    Honors RELAY_JOBS_MODE; in "auto" it tries live and falls back to fixtures so the
    launcher never dead-ends on a blocked scrape.
    """
    terms = [t for t in terms if t.strip()] or ["business operations internship"]
    location = location or config.jobs_location()
    results_wanted = results_wanted or config.jobs_results()
    mode = config.jobs_mode()

    if mode == "fixture":
        return _fixture_scrape(terms, location, results_wanted)
    if mode == "live":
        return _live_scrape(terms, location, results_wanted)
    # auto: try live, fall back to fixtures
    try:
        jobs = _live_scrape(terms, location, results_wanted)
    except Exception:
        jobs = []
    return jobs or _fixture_scrape(terms, location, results_wanted)
