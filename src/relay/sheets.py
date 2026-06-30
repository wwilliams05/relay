"""Tracker adapter: Google Sheets via gspread (PRD §4).

Swap-in alternative: a local .xlsx adapter implementing the same Tracker interface
(openpyxl) — the rest of the app shouldn't care which is active.
"""

from __future__ import annotations

from typing import Protocol

from .models import Contact, Project, Target


class Tracker(Protocol):
    """The interface every storage backend implements (Sheets or local xlsx)."""

    def upsert_target(self, target: Target) -> None: ...
    def write_contacts(self, contacts: list[Contact]) -> None: ...
    def read_contacts(self) -> list[Contact]: ...
    def write_projects(self, projects: list[Project]) -> None: ...


class SheetsTracker:
    """Google Sheets implementation. TODO: open workbook by key, one tab per model."""

    def __init__(self, workbook_key: str) -> None:
        self.workbook_key = workbook_key
        # TODO: gspread.service_account(...).open_by_key(workbook_key)

    def upsert_target(self, target: Target) -> None:
        raise NotImplementedError

    def write_contacts(self, contacts: list[Contact]) -> None:
        raise NotImplementedError

    def read_contacts(self) -> list[Contact]:
        raise NotImplementedError

    def write_projects(self, projects: list[Project]) -> None:
        raise NotImplementedError
