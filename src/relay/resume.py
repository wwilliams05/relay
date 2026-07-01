"""Resume parsing: PDF -> Profile (N0).

`extract_text` is the deterministic half — pull the raw text out of the PDF. The
richer structuring (roles, skills, anchor framing) is best done by the /find-people
skill with the model in the loop; `parse_resume` gives a solid heuristic Profile so the
CLI is runnable on its own and the skill has a starting point to refine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

from . import config
from .models import Profile

# Lines mentioning one of these are treated as a school for the heuristic pass.
_SCHOOL_HINTS = ("university", "college", "institute of technology", "school of")


def extract_text(pdf_path: str | Path) -> str:
    """Return the concatenated text of every page in the resume PDF."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"resume not found: {path}")
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()


def _guess_name(text: str) -> str:
    """First non-empty line is almost always the name on a resume."""
    for line in text.splitlines():
        line = line.strip()
        if line and "@" not in line and not line.lower().startswith("http"):
            return line
    return "(unknown)"


def _guess_schools(text: str) -> list[str]:
    schools: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        low = clean.lower()
        if any(h in low for h in _SCHOOL_HINTS):
            # Trim trailing dates / GPA noise so the school name is clean.
            name = re.split(r"\s{2,}|\s[-–—|]\s|\d{4}", clean)[0].strip(" .,-–—|")
            if name and name not in schools:
                schools.append(name)
    return schools


def parse_resume(pdf_path: str | Path) -> Profile:
    """Extract text and build a heuristic Profile (name + schools).

    Roles/skills are left for the skill layer to enrich; anchor_framing defaults to
    the v1 throughline, 'business operations process improvement'.
    """
    text = extract_text(pdf_path)
    return Profile(name=_guess_name(text), schools=_guess_schools(text))


def save_profile(profile: Profile, path: str | Path | None = None) -> Path:
    """Persist a Profile to JSON so every stage can load it without re-parsing."""
    out = Path(path) if path else config.profile_path()
    out.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return out


def load_profile(path: str | Path | None = None) -> Profile | None:
    src = Path(path) if path else config.profile_path()
    if not src.exists():
        return None
    return Profile.model_validate(json.loads(src.read_text(encoding="utf-8")))
