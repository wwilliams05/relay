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


# --- Profile ----------------------------------------------------------------
# Where the parsed Profile is cached so every stage can load it without re-parsing.
def profile_path() -> Path:
    return ROOT / "profile.json"
