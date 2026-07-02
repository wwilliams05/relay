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


# --- Job discovery (JobSpy + ATS APIs) --------------------------------------
# "live"    -> scrape real job boards via JobSpy (network; may be rate-limited)
# "ats"     -> query official ATS APIs only (targets.yml; reliable, no scraping)
# "fixture" -> canned internship postings so the flow runs fully offline
# "auto"    -> ATS APIs; JobSpy only if ATS is empty, fixtures only if that fails too
#              (so discovery returns fast and never stalls on a blocked scrape)
def jobs_mode() -> str:
    return _env("RELAY_JOBS_MODE", "auto").lower()


def jobs_location() -> str:
    return _env("RELAY_JOBS_LOCATION", "United States")


def jobs_results() -> int:
    raw = _env("RELAY_JOBS_RESULTS", "20")
    return int(raw) if raw.isdigit() else 20


# Drop discovered jobs whose fit score is below this, so the Jobs tab stays focused on
# on-target roles instead of every internship the target companies also post (e.g. the
# engineering roles at a fintech). Set 0 to keep everything.
def jobs_min_fit() -> int:
    raw = _env("RELAY_JOBS_MIN_FIT", "20")
    return int(raw) if raw.lstrip("-").isdigit() else 20


# --- ATS APIs (Greenhouse / Lever / Ashby) ----------------------------------
# Official ATS job-board JSON endpoints for a curated list of target companies.
# Unlike JobSpy (board scraping, rate-limited/blockable), these are free, no-auth,
# and structured. On by default in "auto"/"ats" jobs modes; set RELAY_ATS=0 to skip.
def ats_enabled() -> bool:
    return _env("RELAY_ATS", "1").lower() not in {"0", "false", "no"}


# Where the editable company list lives (overrides the built-in defaults if present).
def ats_targets_path() -> Path:
    raw = _env("RELAY_ATS_TARGETS", "targets.yml")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


# --- Gmail (drafts only — Relay never sends) ---------------------------------
# "live"    -> real Gmail API drafts.create (needs the OAuth client / cached token)
# "fixture" -> write .eml draft files into the local drafts dir; no Google, no network
# "auto"    -> live if Gmail credentials exist on disk, else fixture
def gmail_mode() -> str:
    mode = _env("RELAY_GMAIL_MODE", "auto").lower()
    if mode == "auto":
        has_creds = gmail_token_path().exists() or gmail_client_path().exists()
        return "live" if has_creds else "fixture"
    return mode


def gmail_client_path() -> Path:
    raw = _env("GMAIL_OAUTH_CLIENT", "gmail_client.json")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


def gmail_token_path() -> Path:
    raw = _env("GMAIL_TOKEN_PATH", "gmail.token.json")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


# Where fixture-mode drafts land as .eml files (open them in any mail client).
def drafts_dir() -> Path:
    raw = _env("RELAY_DRAFTS_DIR", "drafts")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


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
    raw = _env("RELAY_PROFILE_PATH", "profile.json")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p
