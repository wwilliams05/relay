"""Job discovery + fit-ranking (N-1).

Turns a Profile (resume + the free-text preferences typed in the launcher) into a
ranked list of postings. Deterministic and offline-friendly: search terms come from
keyword heuristics, and fit-scoring is a transparent rubric rather than a model call —
the /suggest-* skills can refine later, but the launcher never needs an LLM to run.
"""

from __future__ import annotations

from datetime import date

from . import config, jobs
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

_INTERN_HINTS = ("intern", "co-op", "coop", "co op", "summer analyst", "summer associate")

# User-typed preference phrase -> the title keywords that satisfy it. Matched against
# the job *title* (the role), not the whole JD — a JD name-drops every function, so
# full-text matching is what made unrelated roles look like a fit.
_PREF_TITLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "product management": ("product manager", "product management", "associate product manager", "apm"),
    "product manager": ("product manager", "product management", "apm"),
    "apm": ("associate product manager", "apm", "product manager"),
    "bizops": ("business operations", "bizops", "biz ops"),
    "biz ops": ("business operations", "bizops"),
    "business operations": ("business operations", "bizops"),
    "strategy and operations": ("strategy and operations", "strategy & operations", "strategy"),
    "strategy & operations": ("strategy and operations", "strategy & operations", "strategy"),
    "strategy": ("strategy", "strategy and operations"),
    "operations": ("operations",),
    "supply chain": ("supply chain",),
    "finance": ("finance", "financial"),
    "marketing": ("marketing",),
    "growth": ("growth",),
    "consulting": ("consultant", "consulting"),
    "program management": ("program manager", "program management"),
    "project management": ("project manager", "project management"),
}

# Title keywords for business/ops/management-track roles — aligns with a business major
# and counts as a soft positive even when it isn't one of the user's stated preferences.
_BUSINESS_TITLE_KEYWORDS = (
    "business operations", "bizops", "operations", "strategy", "product manager",
    "product management", "program manager", "project manager", "supply chain",
    "procurement", "finance", "financial", "marketing", "growth", "sales", "revenue",
    "consultant", "consulting", "strategist", "business analyst", "management",
    "administration", "go-to-market", "partnerships", "commercial",
)

# Title keywords for roles in a clearly different field from a business/ops track.
# These get a strong penalty so engineering/technical/clinical roles sink.
_OFFTARGET_TITLE_KEYWORDS = (
    "software engineer", "software developer", "backend", "front end", "frontend",
    "full stack", "fullstack", "data engineer", "data scientist", "machine learning",
    "ml engineer", "research scientist", "hardware", "mechanical", "electrical",
    "firmware", "embedded", "robotics", "clinical", "nurse", "physician", "attorney",
    "paralegal", "chemist", "biologist", "technician", "geologist",
    # generic technical / other-field title words (catch Manufacturing Engineer,
    # Naval Architect, Data Scientist, Legal Intern, …)
    "engineer", "architect", "scientist", "legal", "counsel", "designer",
)

# Words in a major that mark it as business/management-adjacent.
_BUSINESS_MAJOR_WORDS = (
    "business", "administration", "management", "finance", "economics", "marketing",
    "operations", "supply chain", "commerce", "accounting",
)

# Location strings too vague to count as "not one of my cities" — don't penalize these.
_AMBIGUOUS_LOCATIONS = (
    "united states", "usa", "u.s.", "multiple", "various", "nationwide", "flexible",
)

# Common ways a preferred city shows up in a posting's location string.
_LOCATION_ALIASES: dict[str, tuple[str, ...]] = {
    "los angeles": ("los angeles", "l.a."),
    "san francisco": ("san francisco", "bay area", "s.f."),
    "new york": ("new york", "nyc", "manhattan", "brooklyn"),
    "st. louis": ("st. louis", "st louis", "saint louis"),
    "st louis": ("st. louis", "st louis", "saint louis"),
    "saint louis": ("st. louis", "st louis", "saint louis"),
    "remote": ("remote", "work from home", "wfh", "anywhere"),
    "hybrid": ("hybrid",),
}


def _location_variants(pref: str) -> tuple[str, ...]:
    p = pref.lower().strip()
    return _LOCATION_ALIASES.get(p, (p,))


def _location_fit(job: Job, prefs: list[str]) -> tuple[int, str | None]:
    """Boost jobs in a preferred location; deprioritize ones clearly elsewhere. Unknown
    or vague locations are left neutral so we don't punish missing data."""
    if not prefs:
        return 0, None
    loc = (job.location or "").strip().lower()
    if not loc:
        return 0, None
    for pref in prefs:
        for variant in _location_variants(pref):
            if variant and variant in loc:
                return 12, f"in {pref}"
    if any(a in loc for a in _AMBIGUOUS_LOCATIONS):
        return 0, None
    return -20, "outside preferred locations"


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


def _is_internship(job: Job) -> bool:
    """Intern/co-op read from title + job_type (not the JD, which can say the opposite)."""
    field = f"{job.title} {job.job_type or ''}".lower()
    return any(h in field for h in _INTERN_HINTS)


def _preferred_title_keywords(notes: str) -> list[str]:
    """Title keywords the user is aiming at, parsed from their 'Looking for' notes."""
    notes = f" {notes.lower()} "
    kws: list[str] = []
    for phrase, keywords in _PREF_TITLE_KEYWORDS.items():
        if phrase in notes:
            for k in keywords:
                if k not in kws:
                    kws.append(k)
    return kws


def _has_business_major(profile: Profile) -> bool:
    """True if the user's major (or notes, as a fallback) reads as business/management."""
    blob = f"{profile.major} {profile.extra_context}".lower()
    return any(w in blob for w in _BUSINESS_MAJOR_WORDS)


def score_job(job: Job, profile: Profile) -> tuple[int, str]:
    """Transparent 0–100 fit score + a one-line reason, judged mostly on the role
    (job title). Typed preferences and a business major are the strongest signals;
    off-field roles (engineering/clinical/…) are penalized so they don't float up."""
    title = job.title.lower()
    reasons: list[str] = []
    score = 50  # neutral baseline

    # 1) Role fit, read from the title. Explicit preference > general business role.
    preferred = _preferred_title_keywords(profile.extra_context)
    pref_hit = next((k for k in preferred if k in title), None)
    biz_hit = next((k for k in _BUSINESS_TITLE_KEYWORDS if k in title), None)
    if pref_hit:
        score += 30
        reasons.append(f"matches your target role ({pref_hit})")
    elif biz_hit:
        score += 12
        reasons.append(f"business/ops role ({biz_hit})")

    # 2) Off-field penalty — engineering/technical/clinical roles are a different track.
    off_hit = next((k for k in _OFFTARGET_TITLE_KEYWORDS if k in title), None)
    if off_hit and not pref_hit:
        score -= 45
        reasons.append(f"off-target field ({off_hit})")

    # 3) Major alignment — a business major reinforces business/ops roles (and further
    #    discounts off-field ones).
    if _has_business_major(profile):
        maj = profile.major or "business major"
        if (pref_hit or biz_hit) and not off_hit:
            score += 12
            reasons.append(f"fits your major ({maj})")
        elif off_hit:
            score -= 8

    # 4) Internship signal — read title + job_type, not the JD (a JD can say
    #    "not an internship", which substring-matching would misread).
    intern_field = f"{job.title} {job.job_type or ''}".lower()
    if not any(h in intern_field for h in _INTERN_HINTS) and _wants_internship(profile):
        score -= 15
        reasons.append("not an internship")

    # 5) Skills overlap — a minor tiebreaker only, and only for on-target roles so a
    #    shared tool (e.g. SQL) can't lift an off-field engineering posting.
    if not off_hit:
        overlap = [s for s in profile.skills if s and s.lower() in title]
        if overlap:
            score += min(6, 2 * len(overlap))
            reasons.append("skills: " + ", ".join(overlap[:3]))

    # 6) Recency — you're likelier to get hired the sooner you apply, so fresher
    #    postings rank higher and stale ones are nudged down.
    if job.date_posted:
        age = (date.today() - job.date_posted).days
        if age <= 7:
            score += 8
            reasons.append("posted this week")
        elif age <= 30:
            score += 4
            reasons.append("posted this month")
        elif age >= 150:
            score -= 6
            reasons.append("stale posting")

    # 7) Location — favor your preferred cities / remote.
    loc_delta, loc_reason = _location_fit(job, profile.preferred_locations)
    score += loc_delta
    if loc_reason:
        reasons.append(loc_reason)

    score = max(0, min(100, score))
    return score, "; ".join(reasons) or "internship match"


def run_discovery(profile: Profile) -> list[Job]:
    """N-1: derive terms -> scrape -> dedup -> fit-rank -> drop off-target. Returns
    ranked Jobs at or above RELAY_JOBS_MIN_FIT (no IO)."""
    terms = derive_search_terms(profile)
    scraped = jobs.scrape(terms)

    seen: dict[str, Job] = {}
    for job in scraped:
        seen.setdefault(job_key(job), job)  # first wins; scrape order is source order

    floor = config.jobs_min_fit()
    wants_intern = _wants_internship(profile)
    ranked: list[Job] = []
    for job in seen.values():
        if wants_intern and not _is_internship(job):
            continue  # v1 is internship-only; drop full-time roles (JobSpy/fixtures)
        job.fit_score, job.fit_reason = score_job(job, profile)
        if job.fit_score >= floor:  # drop engineering/off-field noise from big boards
            ranked.append(job)
    ranked.sort(key=lambda j: j.fit_score, reverse=True)

    # Collapse near-duplicates: the same role+location posted under different URLs
    # (or by two sources). Highest-scored copy is first after the sort, so it wins.
    final: list[Job] = []
    seen_role: set[tuple[str, str, str]] = set()
    for job in ranked:
        key = (job.company.strip().lower(), (job.title or "").strip().lower(),
               (job.location or "").strip().lower())
        if key in seen_role:
            continue
        seen_role.add(key)
        final.append(job)
    return final
