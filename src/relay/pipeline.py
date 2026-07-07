"""Deterministic N2–N4 orchestration: search -> enrich -> classify -> rank.

The LLM-heavy judgment (hook wording, nuanced title derivation) lives in the
/find-people skill; this module is the reproducible spine it calls into so the same
flow also runs straight from the CLI.
"""

from __future__ import annotations

from . import apollo
from .models import Contact, Profile, Target, Why

# Base titles that count as "similar role" for the v1 business-operations throughline.
_BIZOPS_TITLES = [
    "Business Operations", "BizOps", "Strategy & Operations", "Strategy and Operations",
    "Supply Chain", "Product Growth", "Operations Analyst", "Operations Manager",
]


def default_similar_titles(role: str) -> list[str]:
    """Heuristic title expansion for a role (the skill can override with better ones)."""
    titles = list(_BIZOPS_TITLES)
    role_clean = role.strip()
    if role_clean and role_clean not in titles:
        titles.insert(0, role_clean)
    return titles


def priority(contact: Contact, similar_titles: list[str]) -> int:
    """Rank strength per PRD §5 — lower is stronger (sorts first)."""
    title_match = _title_hit(contact.title, similar_titles)
    is_alumni = contact.why == Why.ALUMNI or bool(contact.school_match)
    if contact.why == Why.REFERRAL and contact.referral_cleared:
        return 0
    if is_alumni and title_match:
        return 1
    if is_alumni:
        return 2
    if title_match:
        return 3
    return 4


def _title_hit(title: str | None, similar_titles: list[str]) -> bool:
    if not title:
        return False
    t = title.lower()
    return any(wanted.lower() in t for wanted in similar_titles)


def prioritize(contacts: list[Contact], similar_titles: list[str]) -> list[Contact]:
    """Stable-sort contacts by hook strength (§5), strongest first."""
    return sorted(contacts, key=lambda c: priority(c, similar_titles))


def find_people(
    target: Target,
    profile: Profile,
    per_page: int = 25,
    enrich: bool = True,
    enrich_top: int = 10,
) -> list[Contact]:
    """N2–N4 (minus hook writing): search Apollo, rank by §5, then enrich emails.

    Ranking happens BEFORE enrichment so credits are only spent on the `enrich_top`
    strongest hooks per company (enrichment is the metered Apollo call, PRD §9).
    Hooks are intentionally left unset — writing an individual-specific hook is the
    skill's job (PRD §6). Everything here is deterministic and re-runnable.
    """
    titles = target.similar_titles or default_similar_titles(target.role)
    contacts = apollo.search_people(
        organization=target.company,
        titles=titles,
        schools=profile.schools,
        per_page=per_page,
        domain=target.domain,
    )
    ranked = prioritize(contacts, titles)
    if enrich:
        for c in ranked[:enrich_top]:
            apollo.enrich(c)
    return ranked


def mutuals_nudge(contacts: list[Contact], top_n: int = 5) -> list[str]:
    """Top-N names to manually eyeball on LinkedIn for mutual connections (§5, §7)."""
    return [c.name for c in contacts[:top_n]]
