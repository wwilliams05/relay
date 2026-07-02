"""High-level orchestration shared by the launcher (gui.py) and the CLI.

Each function is one user-visible step and returns plain results so the UI can report
progress. All persistence goes through the active Tracker.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import discover, pipeline, resume
from .models import Contact, Job, Profile, Target
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
