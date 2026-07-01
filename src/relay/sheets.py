"""Tracker adapter (PRD §4).

Two interchangeable backends behind the `Tracker` Protocol:

- `LocalXlsxTracker` — an openpyxl workbook on disk. Default; needs no credentials,
  so the whole N0–N6 funnel is runnable and testable today.
- `SheetsTracker`  — Google Sheets via gspread (drop-in, same interface).

Writes are **upserts**: re-running discovery refreshes the machine-owned columns
(title, email, hook, …) while preserving the human-owned gate columns you've edited
in the tracker (`want_to_message`, `referral_cleared`, funnel state, …).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Protocol

from openpyxl import Workbook, load_workbook

from .models import Contact, EmailStatus, Project, Target, Why


class Tracker(Protocol):
    """The interface every storage backend implements (Sheets or local xlsx)."""

    def upsert_target(self, target: Target) -> None: ...
    def write_contacts(self, contacts: list[Contact]) -> None: ...
    def read_contacts(self) -> list[Contact]: ...
    def update_contact(self, contact: Contact) -> None: ...
    def write_projects(self, projects: list[Project]) -> None: ...
    def read_projects(self) -> list[Project]: ...


# --- Tab schemas: column header -> how to (de)serialize a model field ---------
#
# Each tab is described once, as an ordered list of (header, getter, setter) so the
# workbook layout, the human-facing headers, and the round-trip logic stay in sync.

TARGET_COLUMNS = ["company", "role", "jd_url", "anchor_framing", "status", "similar_titles"]
CONTACT_COLUMNS = [
    "name", "title", "company", "profile_url", "why", "school_match",
    "email", "email_status", "hook", "want_to_message", "referral_cleared",
    "draft_created", "messaged_date", "responded", "chat_notes", "next_step",
]
PROJECT_COLUMNS = [
    "target_company", "for_contact", "project_idea", "skills_shown",
    "interested", "prd_prompt",
]

# Columns a human owns in the tracker; discovery must not clobber these on re-run.
CONTACT_HUMAN_COLUMNS = {
    "want_to_message", "referral_cleared", "draft_created",
    "messaged_date", "responded", "chat_notes", "next_step",
}


def _to_cell(value: Any) -> Any:
    """Model value -> a plain, spreadsheet-friendly cell value."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, (Why, EmailStatus)):
        return value.value
    return value


def _cell_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_bool(value: Any) -> bool:
    return _cell_str(value).upper() in {"TRUE", "1", "YES", "X", "☑", "✓"}


def _as_list(value: Any) -> list[str]:
    s = _cell_str(value)
    return [part.strip() for part in s.split(",") if part.strip()]


def _as_date(value: Any) -> date | None:
    s = _cell_str(value)
    if not s:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(s[:10])


def target_to_row(t: Target) -> dict[str, Any]:
    return {
        "company": t.company, "role": t.role, "jd_url": _to_cell(t.jd_url),
        "anchor_framing": t.anchor_framing, "status": t.status,
        "similar_titles": _to_cell(t.similar_titles),
    }


def contact_to_row(c: Contact) -> dict[str, Any]:
    return {
        "name": c.name, "title": _to_cell(c.title), "company": c.company,
        "profile_url": _to_cell(c.profile_url), "why": _to_cell(c.why),
        "school_match": _to_cell(c.school_match), "email": _to_cell(c.email),
        "email_status": _to_cell(c.email_status), "hook": _to_cell(c.hook),
        "want_to_message": _to_cell(c.want_to_message),
        "referral_cleared": _to_cell(c.referral_cleared),
        "draft_created": _to_cell(c.draft_created),
        "messaged_date": _to_cell(c.messaged_date),
        "responded": _to_cell(c.responded),
        "chat_notes": _to_cell(c.chat_notes), "next_step": _to_cell(c.next_step),
    }


def row_to_contact(row: dict[str, Any]) -> Contact:
    return Contact(
        name=_cell_str(row.get("name")),
        title=_cell_str(row.get("title")) or None,
        company=_cell_str(row.get("company")),
        profile_url=_cell_str(row.get("profile_url")) or None,
        why=Why(_cell_str(row.get("why")) or "similar_role"),
        school_match=_cell_str(row.get("school_match")) or None,
        email=_cell_str(row.get("email")) or None,
        email_status=EmailStatus(_cell_str(row.get("email_status")) or "unavailable"),
        hook=_cell_str(row.get("hook")) or None,
        want_to_message=_as_bool(row.get("want_to_message")),
        referral_cleared=_as_bool(row.get("referral_cleared")),
        draft_created=_as_bool(row.get("draft_created")),
        messaged_date=_as_date(row.get("messaged_date")),
        responded=_as_bool(row.get("responded")),
        chat_notes=_cell_str(row.get("chat_notes")) or None,
        next_step=_cell_str(row.get("next_step")) or None,
    )


def project_to_row(p: Project) -> dict[str, Any]:
    return {
        "target_company": p.target_company, "for_contact": _to_cell(p.for_contact),
        "project_idea": p.project_idea, "skills_shown": _to_cell(p.skills_shown),
        "interested": _to_cell(p.interested), "prd_prompt": _to_cell(p.prd_prompt),
    }


def row_to_project(row: dict[str, Any]) -> Project:
    return Project(
        target_company=_cell_str(row.get("target_company")),
        for_contact=_cell_str(row.get("for_contact")) or None,
        project_idea=_cell_str(row.get("project_idea")),
        skills_shown=_as_list(row.get("skills_shown")),
        interested=_as_bool(row.get("interested")),
        prd_prompt=_cell_str(row.get("prd_prompt")) or None,
    )


def contact_key(c: Contact | dict[str, Any]) -> str:
    """Stable identity for a contact: prefer email, fall back to name+company."""
    get = c.get if isinstance(c, dict) else lambda k: getattr(c, k, None)
    email = _cell_str(get("email"))
    if email:
        return f"email::{email.lower()}"
    return f"nc::{_cell_str(get('name')).lower()}::{_cell_str(get('company')).lower()}"


class LocalXlsxTracker:
    """openpyxl-backed tracker. One workbook, one sheet per model tab."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # -- workbook plumbing ----------------------------------------------------
    def _load(self) -> Workbook:
        if self.path.exists():
            return load_workbook(self.path)
        return Workbook()  # a fresh book with a default "Sheet"

    def _sheet(self, wb: Workbook, title: str, headers: list[str]):
        if title in wb.sheetnames:
            return wb[title]
        # Reuse the default empty sheet openpyxl created, else make a new one.
        default = wb["Sheet"] if "Sheet" in wb.sheetnames and wb["Sheet"].max_row == 1 \
            and wb["Sheet"].max_column == 1 and wb["Sheet"]["A1"].value is None else None
        ws = default or wb.create_sheet(title)
        ws.title = title
        ws.append(headers)
        return ws

    def _read_rows(self, title: str, headers: list[str]) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        wb = load_workbook(self.path, read_only=True)
        if title not in wb.sheetnames:
            return []
        ws = wb[title]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = list(next(rows_iter))
        except StopIteration:
            return []
        header_row = [_cell_str(h) for h in header_row]
        out: list[dict[str, Any]] = []
        for raw in rows_iter:
            if raw is None or all(c is None or _cell_str(c) == "" for c in raw):
                continue
            out.append({h: raw[i] if i < len(raw) else None for i, h in enumerate(header_row)})
        return out

    def _write_rows(self, wb: Workbook, title: str, headers: list[str],
                    rows: list[dict[str, Any]]) -> None:
        # Rebuild the sheet from scratch so column order/headers stay authoritative.
        if title in wb.sheetnames:
            del wb[title]
        ws = self._sheet(wb, title, headers)
        for row in rows:
            ws.append([_to_cell(row.get(h, "")) for h in headers])

    # -- Targets --------------------------------------------------------------
    def upsert_target(self, target: Target) -> None:
        rows = self._read_rows("Targets", TARGET_COLUMNS)
        new = target_to_row(target)
        key = (target.company.lower(), target.role.lower())
        rows = [r for r in rows
                if (_cell_str(r.get("company")).lower(), _cell_str(r.get("role")).lower()) != key]
        rows.append(new)
        wb = self._load()
        self._write_rows(wb, "Targets", TARGET_COLUMNS, rows)
        wb.save(self.path)

    # -- Contacts -------------------------------------------------------------
    def write_contacts(self, contacts: list[Contact]) -> None:
        """Upsert by contact_key, preserving human-owned columns on existing rows."""
        existing = {contact_key(r): r for r in self._read_rows("Contacts", CONTACT_COLUMNS)}
        merged: dict[str, dict[str, Any]] = dict(existing)
        for c in contacts:
            k = contact_key(c)
            row = contact_to_row(c)
            if k in existing:
                for col in CONTACT_HUMAN_COLUMNS:
                    row[col] = existing[k].get(col, row[col])
            merged[k] = row
        wb = self._load()
        self._write_rows(wb, "Contacts", CONTACT_COLUMNS, list(merged.values()))
        wb.save(self.path)

    def read_contacts(self) -> list[Contact]:
        return [row_to_contact(r) for r in self._read_rows("Contacts", CONTACT_COLUMNS)]

    def update_contact(self, contact: Contact) -> None:
        """Overwrite a single contact's row wholesale (used by N5/N6)."""
        rows = self._read_rows("Contacts", CONTACT_COLUMNS)
        k = contact_key(contact)
        rows = [r for r in rows if contact_key(r) != k]
        rows.append(contact_to_row(contact))
        wb = self._load()
        self._write_rows(wb, "Contacts", CONTACT_COLUMNS, rows)
        wb.save(self.path)

    # -- Projects -------------------------------------------------------------
    def write_projects(self, projects: list[Project]) -> None:
        rows = self._read_rows("Projects", PROJECT_COLUMNS)
        rows.extend(project_to_row(p) for p in projects)
        wb = self._load()
        self._write_rows(wb, "Projects", PROJECT_COLUMNS, rows)
        wb.save(self.path)

    def read_projects(self) -> list[Project]:
        return [row_to_project(r) for r in self._read_rows("Projects", PROJECT_COLUMNS)]


class SheetsTracker:
    """Google Sheets implementation (drop-in for LocalXlsxTracker).

    Deferred until the .xlsx flow is dogfooded (PRD §9). Left as an explicit stub so
    flipping RELAY_TRACKER_BACKEND=sheets fails loudly rather than silently.
    """

    def __init__(self, workbook_key: str) -> None:
        self.workbook_key = workbook_key

    def upsert_target(self, target: Target) -> None:
        raise NotImplementedError("SheetsTracker pending; use the default xlsx backend")

    def write_contacts(self, contacts: list[Contact]) -> None:
        raise NotImplementedError("SheetsTracker pending; use the default xlsx backend")

    def read_contacts(self) -> list[Contact]:
        raise NotImplementedError("SheetsTracker pending; use the default xlsx backend")

    def update_contact(self, contact: Contact) -> None:
        raise NotImplementedError("SheetsTracker pending; use the default xlsx backend")

    def write_projects(self, projects: list[Project]) -> None:
        raise NotImplementedError("SheetsTracker pending; use the default xlsx backend")

    def read_projects(self) -> list[Project]:
        raise NotImplementedError("SheetsTracker pending; use the default xlsx backend")


def get_tracker() -> Tracker:
    """Return the active tracker per RELAY_TRACKER_BACKEND (default: local xlsx)."""
    from . import config

    backend = config.tracker_backend()
    if backend == "sheets":
        key = config.sheets_workbook_key()
        if not key:
            raise RuntimeError("SHEETS_WORKBOOK_KEY not set (see .env.example)")
        return SheetsTracker(key)
    if backend == "xlsx":
        return LocalXlsxTracker(config.workbook_path())
    raise RuntimeError(f"unknown RELAY_TRACKER_BACKEND: {backend!r} (expected xlsx|sheets)")
