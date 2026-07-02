"""High-level orchestration shared by the launcher (gui.py) and the CLI.

Each function is one user-visible step and returns plain results so the UI can report
progress. All persistence goes through the active Tracker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import discover, gmail, outreach, pipeline, resume
from .models import Contact, Job, Profile, Project, Target, Why
from .sheets import get_tracker


def parse_locations(raw: str) -> list[str]:
    """Split a free-text locations field on commas/slashes into clean entries."""
    return [p.strip() for p in re.split(r"[,/]", raw) if p.strip()]


def build_profile(
    resume_pdf: str | Path | None, notes: str, locations: str | None = None
) -> Profile:
    """N0: parse the resume (if given) and attach the launcher's free-text notes +
    preferred locations.

    Empty notes/locations preserve the previously saved values, so a no-argument run
    (e.g. the scheduled `relay discover`) keeps using them."""
    if resume_pdf:
        profile = resume.parse_resume(resume_pdf)
    else:
        profile = resume.load_profile() or Profile(name="(unknown)")
    if notes.strip():
        profile.extra_context = notes.strip()
    if locations is not None:
        locs = parse_locations(locations)
        if locs:
            profile.preferred_locations = locs
    resume.save_profile(profile)
    return profile


def discover_jobs(profile: Profile) -> list[Job]:
    """N-1: scrape + fit-rank postings and write them to the Jobs tab (pursue unchecked)."""
    jobs = discover.run_discovery(profile)
    get_tracker().write_jobs(jobs)
    return jobs


def find_people_for_checked_jobs(profile: Profile) -> tuple[list[Contact], list[str]]:
    """N2–N4 for every job the user checked `pursue` on.

    Returns (contacts_written, companies_searched). Skips silently if nothing checked.
    """
    tracker = get_tracker()
    checked = [j for j in tracker.read_jobs() if j.pursue]
    contacts: list[Contact] = []
    companies: list[str] = []
    for job in checked:
        target = Target(
            company=job.company, role=job.title, jd_url=job.job_url,
            similar_titles=pipeline.default_similar_titles(job.title),
        )
        tracker.upsert_target(target)
        contacts.extend(pipeline.find_people(target, profile))
        companies.append(job.company)
    if contacts:
        tracker.write_contacts(contacts)
    return contacts, companies


@dataclass
class DraftRun:
    """What one N5 pass did, so the CLI/GUI can report it faithfully."""

    created: list[tuple[Contact, str]] = field(default_factory=list)  # (contact, draft ref)
    skipped_referrals: list[Contact] = field(default_factory=list)  # uncleared — flagged
    skipped_no_email: list[Contact] = field(default_factory=list)
    rule_violations: list[tuple[Contact, str]] = field(default_factory=list)
    already_drafted: int = 0

    @property
    def nothing_checked(self) -> bool:
        return not (self.created or self.skipped_referrals or self.skipped_no_email
                    or self.rule_violations or self.already_drafted)


def draft_outreach(profile: Profile) -> DraftRun:
    """N5 for every contact the user checked `want_to_message` on.

    Human-gated on both ends: only checked contacts are drafted, and every draft is
    created as a draft (Gmail or local .eml) — never sent. Uncleared referrals are
    skipped and flagged, never named. Sets `draft_created` per contact on success.
    """
    tracker = get_tracker()
    run = DraftRun()
    for contact in tracker.read_contacts():
        if not contact.want_to_message:
            continue
        if contact.draft_created:
            run.already_drafted += 1
            continue
        if contact.why == Why.REFERRAL and not contact.referral_cleared:
            run.skipped_referrals.append(contact)
            continue
        if not contact.email:
            run.skipped_no_email.append(contact)
            continue
        try:
            subject, body = outreach.build_draft(profile, contact)
        except ValueError as exc:
            run.rule_violations.append((contact, str(exc)))
            continue
        ref = gmail.create_draft(contact, subject, body)
        contact.draft_created = True
        tracker.update_contact(contact)
        run.created.append((contact, ref))
    return run


def _match_contact(contacts: list[Contact], name: str) -> Contact:
    """Resolve a human-typed name to exactly one tracked contact, or fail loudly."""
    low = name.strip().lower()
    exact = [c for c in contacts if c.name.lower() == low]
    if len(exact) == 1:
        return exact[0]
    partial = [c for c in contacts if low in c.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise RuntimeError(
            f"no contact matching {name!r} in the Contacts tab — run `relay contacts` "
            "to see who's tracked.")
    raise RuntimeError(
        f"{name!r} is ambiguous — matches: " + ", ".join(c.name for c in partial))


def log_chat(
    name: str,
    *,
    responded: bool | None = None,
    notes: str | None = None,
    next_step: str | None = None,
    messaged_date: date | None = None,
    append_notes: bool = True,
) -> Contact:
    """N6: record what happened with a contact back to the Contacts tab.

    Only the fields you pass change; notes append by default so a second chat never
    silently erases the first. Returns the updated contact.
    """
    tracker = get_tracker()
    contact = _match_contact(tracker.read_contacts(), name)
    if responded is not None:
        contact.responded = responded
    if messaged_date is not None:
        contact.messaged_date = messaged_date
    if notes is not None:
        notes = notes.strip()
        if append_notes and contact.chat_notes and notes:
            contact.chat_notes = f"{contact.chat_notes} | {notes}"
        else:
            contact.chat_notes = notes or contact.chat_notes
    if next_step is not None:
        contact.next_step = next_step.strip() or None
    tracker.update_contact(contact)
    return contact


def add_projects(projects: list[Project]) -> int:
    """N7: write suggested projects to the Projects tab (`interested` unchecked).
    Upserts — re-suggesting the same idea never duplicates or unticks it."""
    if projects:
        get_tracker().write_projects(projects)
    return len(projects)


def fill_prd_prompts(profile: Profile) -> list[Project]:
    """N7 second gate: for every project the user ticked `interested` on that lacks a
    prd_prompt, compose the ready-to-build prompt and persist it. Returns the filled
    projects (empty = nothing was waiting)."""
    tracker = get_tracker()
    projects = tracker.read_projects()
    filled = [p for p in projects if p.interested and not p.prd_prompt]
    for project in filled:
        project.prd_prompt = outreach.project_prd_prompt(project, profile)
    if filled:
        tracker.write_projects(projects)
    return filled
