"""Runtime configuration: env loading, adapter modes, and file paths.

Everything that reads the environment lives here so the adapters stay pure and the
skill-commands have one obvious place to look. `.env` is loaded once on import.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from .env if present; no-op otherwise

# Repo root = two levels up from this file (src/relay/config.py -> repo/).
ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- Apollo -----------------------------------------------------------------
# "live"    -> real httpx calls (needs APOLLO_API_KEY, spends credits)
# "fixture" -> canned local data so the pipeline runs with no key / no credits
# "auto"    -> live if a key is present, else fixture
def apollo_mode() -> str:
    mode = _env("RELAY_APOLLO_MODE", "auto").lower()
    if mode == "auto":
        return "live" if _env("APOLLO_API_KEY") else "fixture"
    return mode


def apollo_key() -> str | None:
    return _env("APOLLO_API_KEY") or None


# --- Job discovery (JobSpy) -------------------------------------------------
# "live"    -> scrape real job boards via JobSpy (network; may be rate-limited)
# "fixture" -> canned internship postings so the flow runs fully offline
# "auto"    -> try live, fall back to fixtures if scraping fails or returns nothing
def jobs_mode() -> str:
    return _env("RELAY_JOBS_MODE", "auto").lower()


def jobs_location() -> str:
    return _env("RELAY_JOBS_LOCATION", "United States")


def jobs_results() -> int:
    raw = _env("RELAY_JOBS_RESULTS", "20")
    return int(raw) if raw.isdigit() else 20


# --- Tracker ----------------------------------------------------------------
# "xlsx"   -> local openpyxl workbook (default; zero credentials)
# "sheets" -> Google Sheets via gspread (needs SHEETS_WORKBOOK_KEY + creds)
def tracker_backend() -> str:
    return _env("RELAY_TRACKER_BACKEND", "xlsx").lower()


def workbook_path() -> Path:
    raw = _env("RELAY_WORKBOOK_PATH", "relay.xlsx")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


def sheets_workbook_key() -> str | None:
    return _env("SHEETS_WORKBOOK_KEY") or None


# Turn boolean gate cells into native Excel checkboxes (Excel 365 / 2024+). On by
# default; set RELAY_XLSX_CHECKBOXES=0 to keep plain TRUE/FALSE if your Excel is older.
def xlsx_checkboxes() -> bool:
    return _env("RELAY_XLSX_CHECKBOXES", "1").lower() not in {"0", "false", "no"}


# --- Profile ----------------------------------------------------------------
# Where the parsed Profile is cached so every stage can load it without re-parsing.
def profile_path() -> Path:
    return ROOT / "profile.json"
