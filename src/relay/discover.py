"""Job discovery + fit-ranking (N-1).

Turns a Profile (resume + the free-text preferences typed in the launcher) into a
ranked list of postings. Deterministic and offline-friendly: search terms come from
keyword heuristics, and fit-scoring is a transparent rubric rather than a model call —
the /suggest-* skills can refine later, but the launcher never needs an LLM to run.
"""

from __future__ import annotations

from . import jobs
from .models import Job, Profile
from .sheets import job_key

# Role phrases we recognize in the user's notes -> the search term we scrape with.
_ROLE_TERMS: dict[str, str] = {
    "product management": "product manager intern",
    "product manager": "product manager intern",
    "apm": "associate product manager intern",
    " pm": "product manager intern",
    "bizops": "business operations intern",
    "business operations": "business operations intern",
    "biz ops": "business operations intern",
    "strategy and operations": "strategy and operations intern",
    "strategy & operations": "strategy and operations intern",
    "operations": "operations intern",
    "supply chain": "supply chain intern",
    "growth": "growth intern",
}

_INTERN_HINTS = ("intern", "co-op", "coop", "co op")
_ANCHOR_HINTS = ("business operations", "process improvement", "operations")


def derive_search_terms(profile: Profile) -> list[str]:
    """Build scrape terms from the notes (preferred) and resume roles (fallback)."""
    notes = f" {profile.extra_context.lower()} "
    terms: list[str] = []
    for phrase, term in _ROLE_TERMS.items():
        if phrase in notes and term not in terms:
            terms.append(term)
    # Fall back to resume roles, then a sane default anchored to the throughline.
    if not terms:
        for role in profile.roles:
            terms.append(f"{role} intern")
    return terms or ["business operations intern"]


def _wants_internship(profile: Profile) -> bool:
    notes = profile.extra_context.lower()
    return any(h in notes for h in _INTERN_HINTS) or True  # v1 is internship-focused


def score_job(job: Job, profile: Profile) -> tuple[int, str]:
    """Transparent 0–100 fit score + a one-line reason."""
    haystack = f"{job.title} {job.description or ''} {job.job_type or ''}".lower()
    notes = profile.extra_context.lower()
    reasons: list[str] = []
    score = 40  # baseline for any scraped match

    # Preferred role match (from the user's notes).
    matched_roles = [p for p in _ROLE_TERMS if p.strip() in notes and p.strip() in haystack]
    if matched_roles:
        score += 25
        reasons.append("matches preferred role")

    # Internship / co-op signal — read the title + job_type, not the description
    # (a JD can say "not an internship", which substring-matching would misread).
    intern_field = f"{job.title} {job.job_type or ''}".lower()
    is_intern = any(h in intern_field for h in _INTERN_HINTS)
    if is_intern:
        score += 20
        reasons.append("internship/co-op")
    elif _wants_internship(profile):
        score -= 20
        reasons.append("not an internship")

    # Anchor / domain keywords.
    if any(h in haystack for h in _ANCHOR_HINTS):
        score += 10
        reasons.append("ops/process-improvement fit")

    # Skills overlap from the resume.
    overlap = [s for s in profile.skills if s and s.lower() in haystack]
    if overlap:
        score += min(15, 5 * len(overlap))
        reasons.append("skills: " + ", ".join(overlap[:3]))

    score = max(0, min(100, score))
    return score, "; ".join(reasons) or "keyword match"


def run_discovery(profile: Profile) -> list[Job]:
    """N-1: derive terms -> scrape -> dedup -> fit-rank. Returns ranked Jobs (no IO)."""
    terms = derive_search_terms(profile)
    scraped = jobs.scrape(terms)

    seen: dict[str, Job] = {}
    for job in scraped:
        seen.setdefault(job_key(job), job)  # first wins; scrape order is source order

    ranked: list[Job] = []
    for job in seen.values():
        job.fit_score, job.fit_reason = score_job(job, profile)
        ranked.append(job)
    ranked.sort(key=lambda j: j.fit_score, reverse=True)
    return ranked
