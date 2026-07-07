"""Apollo adapter: people search + email enrichment (N2, N3).

Docs: https://docs.apollo.io/reference  (People Search + People Match endpoints)

Two modes, selected by `RELAY_APOLLO_MODE` (see config.apollo_mode):
- "live"    — real httpx calls to Apollo. Needs APOLLO_API_KEY; enrichment spends
              credits (PRD §9).
- "fixture" — canned SpaceX/Starlink people so N2–N4 run end to end with no key.

Both modes funnel through `_person_to_contact` so the mapping/classification logic is
identical whether a person came from Apollo or a fixture.
"""

from __future__ import annotations

from typing import Any

import httpx

from . import config
from .models import Contact, EmailStatus, Why

BASE = "https://api.apollo.io/api/v1"

# Apollo's people-search rarely returns education, so alumni classification keys off
# whatever school signal is available (fixtures carry it explicitly under "schools").
_APOLLO_EMAIL_STATUS = {
    "verified": EmailStatus.VERIFIED,
    "likely to engage": EmailStatus.VERIFIED,
    "guessed": EmailStatus.GUESSED,
    "extrapolated": EmailStatus.GUESSED,
    "unavailable": EmailStatus.UNAVAILABLE,
    "unverified": EmailStatus.GUESSED,
}


# --- classification (N2) -----------------------------------------------------
def _person_schools(person: dict[str, Any]) -> list[str]:
    """Best-effort school list from a person object (fixture or live)."""
    schools = list(person.get("schools") or [])
    for edu in person.get("education") or []:
        name = edu.get("school_name") or edu.get("school") if isinstance(edu, dict) else None
        if name:
            schools.append(name)
    return schools


def _school_match(person: dict[str, Any], user_schools: list[str]) -> str | None:
    """Return the first user school this person shares, if any (case-insensitive)."""
    theirs = [s.lower() for s in _person_schools(person)]
    for school in user_schools:
        s = school.lower()
        if any(s in t or t in s for t in theirs):
            return school
    return None


def _title_matches(title: str | None, titles: list[str]) -> bool:
    if not title:
        return False
    t = title.lower()
    return any(wanted.lower() in t for wanted in titles)


def classify_why(person: dict[str, Any], titles: list[str], user_schools: list[str]) -> Why:
    """Alumni signal is the stronger hook, so it wins the `why` label; similar-role
    otherwise. Referral/mutual are never inferred from Apollo (PRD §5, §7)."""
    if _school_match(person, user_schools):
        return Why.ALUMNI
    return Why.SIMILAR_ROLE


def _person_to_contact(
    person: dict[str, Any], organization: str, titles: list[str], user_schools: list[str]
) -> Contact:
    name = person.get("name") or " ".join(
        p for p in (person.get("first_name"), person.get("last_name")) if p
    ).strip()
    org = (person.get("organization") or {}).get("name") if isinstance(
        person.get("organization"), dict
    ) else person.get("organization_name")
    email = person.get("email")
    raw_status = (person.get("email_status") or "").lower()
    status = _APOLLO_EMAIL_STATUS.get(raw_status, EmailStatus.UNAVAILABLE)
    if email and status is EmailStatus.UNAVAILABLE:
        status = EmailStatus.GUESSED
    return Contact(
        name=name or "(unknown)",
        title=person.get("title"),
        company=org or organization,
        profile_url=person.get("linkedin_url"),
        why=classify_why(person, titles, user_schools),
        school_match=_school_match(person, user_schools),
        email=email or None,
        email_status=status,
    )


# --- live Apollo -------------------------------------------------------------
def _client() -> httpx.Client:
    key = config.apollo_key()
    if not key:
        raise RuntimeError("APOLLO_API_KEY not set (see .env.example)")
    return httpx.Client(
        base_url=BASE,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": key,
        },
        timeout=30.0,
    )


def _live_search(
    organization: str, titles: list[str], user_schools: list[str], per_page: int
) -> list[Contact]:
    payload = {
        "q_organization_name": organization,
        "person_titles": titles,
        "page": 1,
        "per_page": per_page,
    }
    with _client() as client:
        resp = client.post("/mixed_people/search", json=payload)
        resp.raise_for_status()
        data = resp.json()
    people = data.get("people") or data.get("contacts") or []
    return [_person_to_contact(p, organization, titles, user_schools) for p in people]


def _live_enrich(contact: Contact) -> Contact:
    first, _, last = contact.name.partition(" ")
    payload: dict[str, Any] = {
        "first_name": first,
        "last_name": last,
        "organization_name": contact.company,
        "reveal_personal_emails": False,
        "reveal_professional_emails": True,
    }
    if contact.profile_url:
        payload["linkedin_url"] = contact.profile_url
    with _client() as client:
        resp = client.post("/people/match", json=payload)
        resp.raise_for_status()
        person = resp.json().get("person") or {}
    email = person.get("email")
    if email:
        raw_status = (person.get("email_status") or "").lower()
        contact.email = email
        contact.email_status = _APOLLO_EMAIL_STATUS.get(raw_status, EmailStatus.GUESSED)
    return contact


# --- fixtures ----------------------------------------------------------------
# Canned SpaceX / Starlink Business Operations people for the v1 dogfood target.
# Mix of USC/WashU alumni and similar-role-only contacts so ranking (N4) has signal.
# INVARIANT: every fixture person's linkedin_url ends in "-example" — that suffix is
# how the tracker recognizes (and, once real people arrive, evicts) sample rows.
_FIXTURE_PEOPLE: list[dict[str, Any]] = [
    {
        "first_name": "Elan", "last_name": "Reyes", "name": "Elan Reyes",
        "title": "Business Operations Analyst, Starlink",
        "organization": {"name": "SpaceX"},
        "linkedin_url": "https://www.linkedin.com/in/elan-reyes-example",
        "schools": ["University of Southern California"],
    },
    {
        "first_name": "Priya", "last_name": "Nandakumar", "name": "Priya Nandakumar",
        "title": "Supply Chain Operations Manager, Starlink",
        "organization": {"name": "SpaceX"},
        "linkedin_url": "https://www.linkedin.com/in/priya-nandakumar-example",
        "schools": ["Washington University in St. Louis"],
    },
    {
        "first_name": "Marcus", "last_name": "Feld", "name": "Marcus Feld",
        "title": "Strategy & Operations Lead, Starlink",
        "organization": {"name": "SpaceX"},
        "linkedin_url": "https://www.linkedin.com/in/marcus-feld-example",
        "schools": ["Stanford University"],
    },
    {
        "first_name": "Dana", "last_name": "Okoro", "name": "Dana Okoro",
        "title": "Product Growth Manager, Starlink",
        "organization": {"name": "SpaceX"},
        "linkedin_url": "https://www.linkedin.com/in/dana-okoro-example",
        "schools": ["University of Southern California"],
    },
    {
        "first_name": "Tomer", "last_name": "Ableson", "name": "Tomer Ableson",
        "title": "Senior Business Operations Manager, Starlink",
        "organization": {"name": "SpaceX"},
        "linkedin_url": "https://www.linkedin.com/in/tomer-ableson-example",
        "schools": ["University of Michigan"],
    },
]

# Deterministic fake emails for fixture enrichment (never hits the network).
_FIXTURE_EMAILS = {
    "Elan Reyes": ("elan.reyes@spacex.com", "verified"),
    "Priya Nandakumar": ("priya.nandakumar@spacex.com", "verified"),
    "Marcus Feld": ("marcus.feld@spacex.com", "guessed"),
    "Dana Okoro": ("dana.okoro@spacex.com", "verified"),
    "Tomer Ableson": ("tomer.ableson@spacex.com", "unavailable"),
}


def _fixture_search(
    organization: str, titles: list[str], user_schools: list[str], per_page: int
) -> list[Contact]:
    matched = [p for p in _FIXTURE_PEOPLE if _title_matches(p.get("title"), titles)] or _FIXTURE_PEOPLE
    return [
        _person_to_contact(p, organization, titles, user_schools)
        for p in matched[:per_page]
    ]


def _fixture_enrich(contact: Contact) -> Contact:
    hit = _FIXTURE_EMAILS.get(contact.name)
    if hit:
        email, raw_status = hit
        status = _APOLLO_EMAIL_STATUS.get(raw_status, EmailStatus.GUESSED)
        if status is not EmailStatus.UNAVAILABLE:
            contact.email = email
        contact.email_status = status
    return contact


# --- public API --------------------------------------------------------------
def search_people(
    organization: str,
    titles: list[str],
    schools: list[str] | None = None,
    per_page: int = 25,
) -> list[Contact]:
    """N2: find people at `organization` matching `titles`, classifying `why` from
    school + title overlap. Mutual-connection detection is out of scope (PRD §7)."""
    schools = schools or []
    if config.apollo_mode() == "fixture":
        return _fixture_search(organization, titles, schools, per_page)
    return _live_search(organization, titles, schools, per_page)


def enrich(contact: Contact) -> Contact:
    """N3: enrich a Contact with a verified email (mutates and returns it)."""
    if config.apollo_mode() == "fixture":
        return _fixture_enrich(contact)
    return _live_enrich(contact)
