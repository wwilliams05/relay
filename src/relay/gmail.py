"""Gmail adapter: create drafts (N5). Relay never sends — it only drafts.

Two modes, selected by `RELAY_GMAIL_MODE` (see config.gmail_mode), mirroring apollo.py:
- "live"    — Gmail API `users.drafts.create` via the OAuth desktop flow. The scope is
              gmail.compose; Relay never calls a send endpoint, so every draft waits
              in your Drafts folder for you to edit and send yourself.
- "fixture" — write the draft as a local .eml file (drafts dir, see config.drafts_dir)
              so the whole N5 flow runs and is testable with no Google credentials.

Auth (live): OAuth desktop client json at GMAIL_OAUTH_CLIENT; the granted token is
cached at GMAIL_TOKEN_PATH (*.token.json is gitignored). Needs the optional deps:
`pip install google-api-python-client google-auth-oauthlib`.
"""

from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from pathlib import Path

from . import config
from .models import Contact

# Compose-only: may create/update drafts. Relay never requests a send-capable flow
# beyond it, and never calls users.messages.send / users.drafts.send.
_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def _mime(contact: Contact, subject: str, body: str) -> EmailMessage:
    if not contact.email:
        raise ValueError(f"{contact.name} has no email — enrich before drafting")
    msg = EmailMessage()
    msg["To"] = str(contact.email)
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


# --- fixture (local .eml files) ------------------------------------------------
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "draft"


def _fixture_create_draft(contact: Contact, subject: str, body: str) -> str:
    out_dir = config.drafts_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    msg = _mime(contact, subject, body)
    msg["X-Relay"] = "draft only; Relay never sends"  # ASCII: header survives round-trip
    path = out_dir / f"{_slug(f'{contact.company}-{contact.name}')}.eml"
    path.write_bytes(bytes(msg))
    return str(path)


# --- live (Gmail API) ------------------------------------------------------------
def _live_credentials():
    """Cached-token-first OAuth desktop flow. Imports are lazy so fixture mode never
    needs the Google client libraries installed."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Gmail live mode needs the Google client libraries — "
            "pip install google-api-python-client google-auth-oauthlib "
            "(or set RELAY_GMAIL_MODE=fixture)."
        ) from exc

    token_path = config.gmail_token_path()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        client_path = config.gmail_client_path()
        if not client_path.exists():
            raise RuntimeError(
                f"Gmail OAuth client not found at {client_path} — download a desktop "
                "OAuth client json from Google Cloud Console and set GMAIL_OAUTH_CLIENT "
                "(see .env.example), or set RELAY_GMAIL_MODE=fixture."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_path), _SCOPES)
        creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _live_create_draft(contact: Contact, subject: str, body: str) -> str:
    from googleapiclient.discovery import build  # lazy; optional dependency

    service = build("gmail", "v1", credentials=_live_credentials())
    raw = base64.urlsafe_b64encode(bytes(_mime(contact, subject, body))).decode("ascii")
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    return str(draft.get("id") or "")


# --- public API -------------------------------------------------------------------
def create_draft(contact: Contact, subject: str, body: str) -> str:
    """Create a draft addressed to `contact`; never send it.

    Returns a reference you can chase: the Gmail draft id (live) or the .eml file
    path (fixture). Sending stays a human action in the Gmail UI.
    """
    if config.gmail_mode() == "fixture":
        return _fixture_create_draft(contact, subject, body)
    return _live_create_draft(contact, subject, body)


def drafts_location() -> str:
    """Human-readable place to find the drafts this run created."""
    if config.gmail_mode() == "fixture":
        return str(config.drafts_dir())
    return "Gmail → Drafts"
