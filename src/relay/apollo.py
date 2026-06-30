"""Apollo adapter: people search + email enrichment (N2, N3).

Docs: https://docs.apollo.io/reference  (People Search + People Enrichment endpoints)
Set APOLLO_API_KEY in .env. Each enrichment consumes credits — see PRD §9.
"""

from __future__ import annotations

import os

import httpx

from .models import Contact, EmailStatus, Why

BASE = "https://api.apollo.io/api/v1"


def _key() -> str:
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        raise RuntimeError("APOLLO_API_KEY not set (see .env.example)")
    return key


def search_people(
    organization: str,
    titles: list[str],
    schools: list[str] | None = None,
    per_page: int = 25,
) -> list[Contact]:
    """N2: find people at `organization` matching titles / schools.

    TODO: call POST /mixed_people/search with organization + person_titles filters.
    Map each result to a Contact, classifying `why` (alumni / similar_role) from the
    school + title overlap. Mutual-connection detection is intentionally out of scope (PRD §7).
    """
    raise NotImplementedError("wire up Apollo people search")


def enrich(contact: Contact) -> Contact:
    """N3: enrich a Contact with a verified email.

    TODO: call POST /people/match, set contact.email + contact.email_status.
    """
    raise NotImplementedError("wire up Apollo enrichment")
