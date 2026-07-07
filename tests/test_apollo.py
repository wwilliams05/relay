"""Live Apollo client contract (mocked transport — no network, no credits)."""

from __future__ import annotations

import json

import httpx
import pytest

from relay import apollo, pipeline
from relay.models import Profile, Target

_PERSON = {
    "name": "Elan Reyes", "title": "Business Operations Analyst",
    "organization": {"name": "SpaceX"},
    "linkedin_url": "https://www.linkedin.com/in/elan-reyes",
    "email_status": "verified",
}


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(base_url=apollo.BASE, transport=httpx.MockTransport(handler))


@pytest.fixture()
def live(monkeypatch):
    monkeypatch.setenv("RELAY_APOLLO_MODE", "live")
    return monkeypatch


def test_live_search_uses_domain_scoping_not_org_name(live) -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"people": [_PERSON]})

    live.setattr(apollo, "_client", lambda: _mock_client(handler))
    contacts = apollo.search_people(
        "SpaceX", ["Business Operations"], schools=["USC"], per_page=5,
        domain="spacex.com")

    (payload,) = payloads
    # The documented People Search contract: domains list, not q_organization_name
    # (which the endpoint ignores, returning people from ANY company).
    assert payload["q_organization_domains_list"] == ["spacex.com"]
    assert "q_organization_name" not in payload
    assert payload["person_titles"] == ["Business Operations"]
    assert payload["include_similar_titles"] is True
    assert payload["per_page"] == 5
    assert [c.name for c in contacts] == ["Elan Reyes"]


def test_live_search_falls_back_to_keywords(live) -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        if "q_organization_domains_list" in payload:
            return httpx.Response(200, json={"people": []})  # domain finds no one
        return httpx.Response(200, json={"people": [_PERSON]})

    live.setattr(apollo, "_client", lambda: _mock_client(handler))
    contacts = apollo.search_people("SpaceX", ["Business Operations"],
                                    domain="wrong-domain.com")
    assert len(payloads) == 2
    assert payloads[1]["q_keywords"] == "SpaceX"
    assert [c.name for c in contacts] == ["Elan Reyes"]


def test_live_search_filters_wrong_employers(live) -> None:
    stranger = {**_PERSON, "name": "Wrong Person",
                "organization": {"name": "Totally Unrelated Corp"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"people": [_PERSON, stranger]})

    live.setattr(apollo, "_client", lambda: _mock_client(handler))
    contacts = apollo.search_people("SpaceX", ["Business Operations"], domain="spacex.com")
    assert [c.name for c in contacts] == ["Elan Reyes"]


def test_live_search_surfaces_apollo_plan_errors(live) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={
            "error": "api/v1/mixed_people/search is not accessible on a free plan."})

    live.setattr(apollo, "_client", lambda: _mock_client(handler))
    with pytest.raises(RuntimeError, match="free plan"):
        apollo.search_people("SpaceX", ["Business Operations"], domain="spacex.com")


def test_find_people_enriches_only_top_ranked(profile: Profile, monkeypatch) -> None:
    enriched: list[str] = []
    monkeypatch.setattr(pipeline.apollo, "enrich",
                        lambda c: enriched.append(c.name) or c)
    target = Target(company="SpaceX", role="Business Operations Co-Op")
    ranked = pipeline.find_people(target, profile, enrich_top=2)  # fixture search
    assert len(ranked) > 2
    assert enriched == [c.name for c in ranked[:2]]  # credits go to the best hooks
