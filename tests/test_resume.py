"""Résumé heuristics (relay.resume): name / school / major extraction from raw text."""

from __future__ import annotations

from relay.resume import _guess_major, _guess_name, _guess_schools

SAMPLE = """Weston Williams
Los Angeles, CA | westonwi@example.edu | (555) 555-5555

EDUCATION
University of Southern California, Marshall School of Business    Los Angeles, CA
B.S. in Business Administration and a Minor in Applied Analytics    May 2028
Washington University in St. Louis    2023 - 2024

EXPERIENCE
Acme Logistics - Operations Intern    Summer 2025
• Led a university outreach program improving process throughput 15%

SKILLS
SQL, Excel, Tableau
"""


def test_guess_name_is_first_real_line() -> None:
    assert _guess_name(SAMPLE) == "Weston Williams"
    assert _guess_name("jane@x.com\nhttps://site\nJane Doe\n") == "Jane Doe"
    assert _guess_name("") == "(unknown)"


def test_guess_schools_bounded_to_education_section() -> None:
    schools = _guess_schools(SAMPLE)
    assert schools == [
        "University of Southern California",
        "Washington University in St. Louis",
    ]
    # The "university outreach" experience bullet must not leak in.
    assert all("outreach" not in s.lower() for s in schools)


def test_guess_schools_without_education_header_scans_everything() -> None:
    text = "Jane Doe\nUniversity of Michigan    Ann Arbor, MI\n"
    assert _guess_schools(text) == ["University of Michigan"]


def test_guess_major_from_degree_line() -> None:
    assert _guess_major(SAMPLE) == "Business Administration"
    assert _guess_major("Bachelor of Arts in Economics, GPA 3.9") == "Economics"
    assert _guess_major("B.B.A. in Supply Chain Management | Dean's List") == (
        "Supply Chain Management")


def test_guess_major_known_major_fallback_and_empty() -> None:
    assert _guess_major("Currently studying Finance at a large university") == "Finance"
    assert _guess_major("no degree information here") == ""
