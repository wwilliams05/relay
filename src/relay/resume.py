"""Resume parsing: PDF -> Profile (N0)."""

from __future__ import annotations

from pathlib import Path

from .models import Profile


def parse_resume(pdf_path: str | Path) -> Profile:
    """Extract text (pdfplumber), then LLM-extract into a Profile.

    TODO: pull raw text, hand it to the model with the Profile schema, return Profile.
    Keep anchor_framing defaulting to 'business operations process improvement'.
    """
    raise NotImplementedError("wire up resume parsing")
