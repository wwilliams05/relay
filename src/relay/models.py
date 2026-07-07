"""Core data models for Relay. These mirror the tracker tabs in docs/PRD.md §4."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class Why(str, Enum):
    """Why this person is worth reaching out to (drives prioritization, §5)."""

    REFERRAL = "referral"
    ALUMNI = "alumni"
    SIMILAR_ROLE = "similar_role"
    MUTUAL = "mutual"


class EmailStatus(str, Enum):
    VERIFIED = "verified"
    GUESSED = "guessed"
    UNAVAILABLE = "unavailable"


class Profile(BaseModel):
    """Parsed from the user's resume (N0)."""

    name: str
    schools: list[str] = Field(default_factory=list)
    major: str = ""  # field of study, e.g. "Business Administration"; weights job fit
    roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    # Preferred work locations (e.g. ["Los Angeles", "New York", "Remote"]); jobs in
    # these rank higher and jobs clearly elsewhere are deprioritized in discovery.
    preferred_locations: list[str] = Field(default_factory=list)
    anchor_framing: str = "business operations process improvement"
    # Free-text preferences the user typed in the launcher that aren't on the resume
    # (e.g. "Fall 2026 Co-Op, Product Management or BizOps"). Drives job discovery.
    extra_context: str = ""


class Target(BaseModel):
    """A company + role you're pursuing (N1)."""

    company: str
    role: str
    jd_url: str | None = None
    anchor_framing: str = "business operations process improvement"
    status: str = "active"
    # Titles that count as "similar role" for people discovery (N2).
    similar_titles: list[str] = Field(default_factory=list)
    # Company website domain (e.g. "spacex.com") — scopes Apollo people search to the
    # right org. Sourced from targets.yml; plumbing only, not written to the tab.
    domain: str | None = None


class Contact(BaseModel):
    """A person at a target company (N2–N6)."""

    name: str
    title: str | None = None
    company: str
    profile_url: str | None = None
    why: Why
    school_match: str | None = None
    email: EmailStr | None = None
    email_status: EmailStatus = EmailStatus.UNAVAILABLE
    hook: str | None = None  # the individual-specific opener (§6)

    # Human gates / funnel state
    want_to_message: bool = False
    referral_cleared: bool = False
    draft_created: bool = False
    messaged_date: date | None = None
    responded: bool = False
    chat_notes: str | None = None
    next_step: str | None = None


class Job(BaseModel):
    """A scraped job/internship posting (N-1, job discovery). Feeds the Jobs tab.

    Populated by the jobs adapter (JobSpy) and fit-ranked against the Profile before
    the user checks which ones to pursue.
    """

    company: str
    title: str
    location: str | None = None
    job_type: str | None = None  # internship, fulltime, contract, ...
    source: str | None = None  # indeed, linkedin, glassdoor, ...
    job_url: str | None = None
    date_posted: date | None = None
    fit_score: int = 0  # 0–100 heuristic match to the Profile
    fit_reason: str | None = None  # one line: why it scored that way
    description: str | None = None  # scraped JD text; used for fit-scoring, not persisted

    # Human gate: check the jobs you want Relay to find people for.
    pursue: bool = False
    status: str = "new"


class Project(BaseModel):
    """A portfolio project idea tied to a contact (N7)."""

    target_company: str
    for_contact: str | None = None
    project_idea: str
    skills_shown: list[str] = Field(default_factory=list)
    interested: bool = False
    prd_prompt: str | None = None
