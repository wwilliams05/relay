"""Gmail adapter: create drafts (N5). Relay never sends — it only drafts.

Auth: Gmail API OAuth desktop flow (or workspace service account). Scope:
https://www.googleapis.com/auth/gmail.compose  (compose-only; cannot send).
"""

from __future__ import annotations

from .models import Contact


def create_draft(contact: Contact, subject: str, body: str) -> str:
    """Create a Gmail draft addressed to `contact`. Returns the draft id.

    TODO: build a MIME message, base64url-encode, POST to
    users.drafts.create. Do NOT call drafts.send — sending stays manual.
    """
    raise NotImplementedError("wire up Gmail drafts")
