"""Job-discovery adapter: postings from ATS APIs + JobSpy (N-1).

Two independent sources, selected by `RELAY_JOBS_MODE` (see config.jobs_mode):
- ATS APIs — official job-board JSON endpoints (Greenhouse / Lever / Ashby) for a
             curated list of target companies (targets.yml). Free, no-auth, structured,
             and — unlike scraping — never rate-limited or blocked. Reliable discovery.
- JobSpy   — scrape real boards (Indeed / LinkedIn / Google / ZipRecruiter). Broad
             coverage across every company, but network-bound and often rate-limited.

Modes: "ats" (ATS only), "live" (JobSpy only), "fixture" (canned, fully offline),
"auto" (ATS, falling back to JobSpy then fixtures only if ATS is empty — so the
launcher never stalls on a blocked scrape).

Every posting funnels through `_normalize` so ATS, JobSpy, and fixture rows map to a
Job the same way. Fit-scoring against the Profile happens in `relay.discover`.
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Any

from . import config
from .models import Job

_DEFAULT_SITES = ["indeed", "linkedin", "google", "zip_recruiter"]

# Titles we keep from an ATS board (which lists *every* open role): v1 is
# internship-focused, so we gate on this and let fit-scoring rank the rest. Word
# boundaries matter — a bare "intern" substring would wrongly catch "Internal Audit".
_INTERN_TITLE_RE = re.compile(r"\b(intern(?:ship)?s?|co[- ]?ops?)\b", re.IGNORECASE)


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    # Lever posts epoch-milliseconds timestamps; treat plain numbers as those.
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date()
        except (ValueError, OverflowError, OSError):
            return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _strip_html(text: Any) -> str | None:
    """Roughly de-tag an HTML JD to plain text — enough for keyword fit-scoring."""
    if not text:
        return None
    plain = re.sub(r"<[^>]+>", " ", str(text))
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip() or None


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


# --- ATS APIs (Greenhouse / Lever / Ashby) -----------------------------------
# Curated target companies queried via their official ATS job-board endpoints.
# Verified live (2026-07). Extend/override this list in targets.yml at the repo root;
# each entry needs {company, provider, token} where token is the board slug in the
# ATS URL (e.g. greenhouse.io/boards/<token>, jobs.ashbyhq.com/<token>).
_DEFAULT_ATS_TARGETS: list[dict[str, str]] = [
    {"company": "Stripe", "provider": "greenhouse", "token": "stripe"},
    {"company": "DoorDash", "provider": "greenhouse", "token": "doordashusa"},
    {"company": "Databricks", "provider": "greenhouse", "token": "databricks"},
    {"company": "Anduril", "provider": "greenhouse", "token": "andurilindustries"},
    {"company": "Coinbase", "provider": "greenhouse", "token": "coinbase"},
    {"company": "Airbnb", "provider": "greenhouse", "token": "airbnb"},
    {"company": "Notion", "provider": "ashby", "token": "notion"},
    {"company": "Ramp", "provider": "ashby", "token": "Ramp"},
    {"company": "OpenAI", "provider": "ashby", "token": "openai"},
    {"company": "Palantir", "provider": "lever", "token": "palantir"},
]

_ATS_TIMEOUT = 20.0
_ATS_HEADERS = {"User-Agent": "Relay/1 (job-discovery; +https://github.com/relay)"}


def _load_ats_targets() -> list[dict[str, str]]:
    """Built-in target list, replaced wholesale by targets.yml if it exists + parses."""
    path = config.ats_targets_path()
    if not path.exists():
        return _DEFAULT_ATS_TARGETS
    try:
        import yaml  # optional dep; degrade to defaults if unavailable

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        targets = loaded.get("targets", []) if isinstance(loaded, dict) else loaded
        cleaned = [
            {"company": str(t["company"]), "provider": str(t["provider"]).lower(),
             "token": str(t["token"])}
            for t in targets
            if isinstance(t, dict) and t.get("company") and t.get("provider") and t.get("token")
        ]
        return cleaned or _DEFAULT_ATS_TARGETS
    except Exception:
        return _DEFAULT_ATS_TARGETS


def _ats_get(url: str) -> Any:
    import httpx

    with httpx.Client(timeout=_ATS_TIMEOUT, follow_redirects=True, headers=_ATS_HEADERS) as c:
        resp = c.get(url)
        resp.raise_for_status()
        return resp.json()


def _greenhouse_rows(company: str, token: str) -> list[dict[str, Any]]:
    data = _ats_get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    rows = []
    for j in data.get("jobs", []):
        rows.append({
            "company": company, "title": j.get("title"),
            "location": (j.get("location") or {}).get("name"),
            "site": "greenhouse", "job_url": j.get("absolute_url"),
            "date_posted": j.get("updated_at") or j.get("first_published"),
            "description": _strip_html(j.get("content")),
        })
    return rows


def _lever_rows(company: str, token: str) -> list[dict[str, Any]]:
    data = _ats_get(f"https://api.lever.co/v0/postings/{token}?mode=json")
    rows = []
    for j in data or []:
        cats = j.get("categories") or {}
        rows.append({
            "company": company, "title": j.get("text"),
            "location": cats.get("location"), "job_type": cats.get("commitment"),
            "site": "lever", "job_url": j.get("hostedUrl") or j.get("applyUrl"),
            "date_posted": j.get("createdAt"),
            "description": j.get("descriptionPlain") or _strip_html(j.get("description")),
        })
    return rows


def _ashby_rows(company: str, token: str) -> list[dict[str, Any]]:
    data = _ats_get(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    rows = []
    for j in data.get("jobs", []):
        rows.append({
            "company": company, "title": j.get("title"),
            "location": j.get("location"), "job_type": j.get("employmentType"),
            "site": "ashby", "job_url": j.get("jobUrl") or j.get("applyUrl"),
            "date_posted": j.get("publishedDate") or j.get("publishedAt"),
            "description": j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml")),
        })
    return rows


_ATS_PROVIDERS = {
    "greenhouse": _greenhouse_rows,
    "lever": _lever_rows,
    "ashby": _ashby_rows,
}


def _fetch_target(target: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch one company's postings. Best-effort: a bad slug / blocked board / blip on
    one company is swallowed so the rest still return."""
    fetch = _ATS_PROVIDERS.get(target["provider"])
    if fetch is None:
        return []
    try:
        return fetch(target["company"], target["token"])
    except Exception:
        return []


def _ats_scrape(terms: list[str], location: str, results_wanted: int) -> list[Job]:
    """Query every target company's ATS in parallel (network-bound), keep the
    internship-titled roles, and normalize to Jobs. Fit-scoring/ranking happens
    downstream in `relay.discover`.
    """
    if not config.ats_enabled():
        return []
    targets = _load_ats_targets()
    if not targets:
        return []
    jobs: list[Job] = []
    # Boards are independent IO — fan out so 40 companies take ~one slow request, not 40.
    with ThreadPoolExecutor(max_workers=min(12, len(targets))) as pool:
        for rows in pool.map(_fetch_target, targets):
            for row in rows:
                if _INTERN_TITLE_RE.search(str(row.get("title") or "")):
                    jobs.append(_normalize(row))
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
    """N-1: gather postings for `terms`. Returns raw (unranked, un-deduped) Jobs.

    Honors RELAY_JOBS_MODE; in "auto" it merges the reliable ATS APIs with JobSpy's
    breadth and falls back to fixtures so the launcher never dead-ends on a blocked
    scrape. Dedup + fit-ranking happen in `relay.discover`.
    """
    terms = [t for t in terms if t.strip()] or ["business operations internship"]
    location = location or config.jobs_location()
    results_wanted = results_wanted or config.jobs_results()
    mode = config.jobs_mode()

    if mode == "fixture":
        return _fixture_scrape(terms, location, results_wanted)
    if mode == "ats":
        return _ats_scrape(terms, location, results_wanted)
    if mode == "live":
        return _live_scrape(terms, location, results_wanted)
    # auto: ATS is the reliable primary. Only fall through to JobSpy's board scraping if
    # ATS came up empty — a blocked/slow scrape must never stall the launcher — and to
    # fixtures only if that fails too. So `auto` returns quickly whenever ATS has results.
    jobs = _ats_scrape(terms, location, results_wanted)
    if not jobs:
        try:
            jobs = _live_scrape(terms, location, results_wanted)
        except Exception:
            jobs = []
    return jobs or _fixture_scrape(terms, location, results_wanted)
