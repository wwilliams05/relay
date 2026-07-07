"""SheetsTracker against an in-memory gspread fake (real Sheets returns every cell
as a string, so the fake renders values the way the API would)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from relay.models import Contact, EmailStatus, Job, Project, Why
from relay.sheets import SheetsTracker, get_tracker


class FakeWorksheet:
    def __init__(self) -> None:
        self._values: list[list[Any]] = []

    def get_all_values(self) -> list[list[str]]:
        def cell(v: Any) -> str:
            if v is None:
                return ""
            if v is True:
                return "TRUE"
            if v is False:
                return "FALSE"
            return str(v)
        return [[cell(v) for v in row] for row in self._values]

    def clear(self) -> None:
        self._values = []

    def update(self, values: list[list[Any]] | None = None,
               range_name: str | None = None) -> None:
        assert range_name == "A1"
        self._values = [list(row) for row in values or []]


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.sheets: dict[str, FakeWorksheet] = {}

    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self.sheets:
            raise KeyError(title)
        return self.sheets[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        ws = FakeWorksheet()
        self.sheets[title] = ws
        return ws


class FakeClient:
    def __init__(self) -> None:
        self.spreadsheet = FakeSpreadsheet()

    def open_by_key(self, key: str) -> FakeSpreadsheet:
        return self.spreadsheet


@pytest.fixture()
def sheets() -> SheetsTracker:
    return SheetsTracker("fake-key", client=FakeClient())


def _tick(tracker: SheetsTracker, sheet: str, key_header: str, key_value: str,
          bool_header: str) -> None:
    """Simulate the human ticking a checkbox in the Google Sheets UI."""
    ws = tracker._client.spreadsheet.sheets[sheet]
    headers = ws._values[0]
    key_col, bool_col = headers.index(key_header), headers.index(bool_header)
    for row in ws._values[1:]:
        if str(row[key_col]) == key_value:
            row[bool_col] = True


def test_sheets_contacts_round_trip(sheets: SheetsTracker) -> None:
    original = Contact(
        name="Elan Reyes", title="BizOps Analyst", company="SpaceX", why=Why.ALUMNI,
        school_match="University of Southern California", email="elan.reyes@spacex.com",
        email_status=EmailStatus.VERIFIED, hook="USC grad now in Starlink ops",
        want_to_message=True, messaged_date=date(2026, 7, 1), responded=True,
        chat_notes="Great chat", next_step="Send thank-you")
    sheets.write_contacts([original])
    (read,) = sheets.read_contacts()
    assert read == original


def test_sheets_preserves_human_columns_on_rerun(sheets: SheetsTracker) -> None:
    sheets.write_contacts([Contact(name="Elan Reyes", company="SpaceX", why=Why.ALUMNI,
                                   email="elan.reyes@spacex.com")])
    _tick(sheets, "Contacts", "name", "Elan Reyes", "want_to_message")
    sheets.write_contacts([Contact(name="Elan Reyes", company="SpaceX", why=Why.ALUMNI,
                                   email="elan.reyes@spacex.com", title="Senior Analyst")])
    (read,) = sheets.read_contacts()
    assert read.want_to_message is True
    assert read.title == "Senior Analyst"


def test_sheets_jobs_sort_prune_and_pursue(sheets: SheetsTracker) -> None:
    sheets.write_jobs([
        Job(company="A", title="Ops Intern", job_url="https://x/1", fit_score=30),
        Job(company="B", title="PM Intern", job_url="https://x/2", fit_score=90),
        Job(company="C", title="Noise", job_url="https://x/3", fit_score=5),  # < floor 20
    ])
    assert [j.fit_score for j in sheets.read_jobs()] == [90, 30]

    _tick(sheets, "Jobs", "company", "B", "pursue")
    sheets.write_jobs([Job(company="B", title="PM Intern", job_url="https://x/2",
                           fit_score=95)])
    top = sheets.read_jobs()[0]
    assert (top.company, top.fit_score, top.pursue) == ("B", 95, True)


def test_sheets_projects_upsert(sheets: SheetsTracker) -> None:
    idea = Project(target_company="SpaceX", project_idea="Ops dashboard",
                   skills_shown=["SQL"])
    sheets.write_projects([idea])
    sheets.write_projects([idea])
    assert len(sheets.read_projects()) == 1


def test_sheets_backend_requires_workbook_key(monkeypatch) -> None:
    monkeypatch.setenv("RELAY_TRACKER_BACKEND", "sheets")
    monkeypatch.setenv("SHEETS_WORKBOOK_KEY", "")
    with pytest.raises(RuntimeError, match="SHEETS_WORKBOOK_KEY"):
        get_tracker()


def test_sheets_live_auth_fails_loudly_without_creds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    with pytest.raises(RuntimeError, match="service-account json not found"):
        SheetsTracker("some-key").read_jobs()
