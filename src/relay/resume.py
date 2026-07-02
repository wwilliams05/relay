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

# Other section headers — used to bound the Education block so a "university" mention
# in an experience/research bullet isn't mistaken for a school the user attended.
_OTHER_SECTIONS = (
    "experience", "work experience", "professional experience", "employment",
    "projects", "technical projects", "skills", "technical skills", "leadership",
    "activities", "leadership & activities", "awards", "honors", "certifications",
    "volunteer", "interests", "summary", "objective", "publications", "research",
    "extracurricular", "involvement",
)

# Degree line like "B.S. in Business Administration" / "Bachelor of Arts in Economics".
_DEGREE_RE = re.compile(
    r"\b(?:B\.?S\.?|B\.?A\.?|B\.?B\.?A\.?|Bachelor(?:'s)?(?:\s+of\s+[A-Za-z]+)?)\b"
    r"[^\n,;]*?\b(?:in|of)\s+([A-Za-z][A-Za-z&/ ]{2,40})",
    re.IGNORECASE,
)
# Majors we'll also recognize if they appear verbatim (fallback when the degree line
# isn't phrased "... in <major>").
_KNOWN_MAJORS = (
    "Business Administration", "Business Analytics", "Finance", "Economics",
    "Marketing", "Management", "Accounting", "Supply Chain Management",
    "Industrial Engineering", "Computer Science", "Data Science",
)


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


def _education_lines(text: str) -> list[str]:
    """The lines under an 'Education' heading, up to the next section — so school
    detection ignores 'university' mentions elsewhere (e.g. research bullets)."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        s = line.strip().rstrip(":").lower()
        if s == "education" or s.startswith("education "):
            start = i + 1
            break
    if start is None:
        return lines  # no explicit section — fall back to scanning everything
    block: list[str] = []
    for line in lines[start:]:
        s = line.strip().rstrip(":").lower()
        is_header = s in _OTHER_SECTIONS or (line.strip().isupper() and 2 < len(line.strip()) < 30)
        if is_header:
            break
        block.append(line)
    return block


def _guess_schools(text: str) -> list[str]:
    schools: list[str] = []
    for line in _education_lines(text):
        clean = line.strip()
        low = clean.lower()
        # A real school line names an institution; skip prose bullets that merely
        # mention a university (those are long or start with a bullet glyph).
        if clean[:1] in "•▪◦-*":
            continue
        if any(h in low for h in _SCHOOL_HINTS):
            # Trim trailing location / dates / GPA noise so the school name is clean.
            name = re.split(r"\s{2,}|\s[-–—|]\s|,|\d{4}", clean)[0].strip(" .,-–—|")
            if name and name not in schools:
                schools.append(name)
    return schools


def _guess_major(text: str) -> str:
    """Best-effort field of study from a degree line, else a known-major mention."""
    m = _DEGREE_RE.search(text)
    if m:
        major = re.split(r"\s{2,}|\||;", m.group(1))[0].strip(" .,-–—")
        # Drop a trailing "and Minor…"/"with…" tail the regex may have swept in.
        major = re.split(r"\band\b|\bwith\b|\bminor\b", major, flags=re.IGNORECASE)[0].strip()
        if major:
            return major.title()
    low = text.lower()
    for major in _KNOWN_MAJORS:
        if major.lower() in low:
            return major
    return ""


def parse_resume(pdf_path: str | Path) -> Profile:
    """Extract text and build a heuristic Profile (name + schools + major).

    Roles/skills are left for the skill layer to enrich; anchor_framing defaults to
    the v1 throughline, 'business operations process improvement'.
    """
    text = extract_text(pdf_path)
    return Profile(
        name=_guess_name(text),
        schools=_guess_schools(text),
        major=_guess_major(text),
    )


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
