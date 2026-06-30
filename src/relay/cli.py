"""Thin CLI. The real orchestration lives in .claude/commands/ (Claude Code skills);
this exposes the deterministic helpers so skills (and you) can call them directly.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Relay — networking outreach orchestrator")


@app.command()
def find(company: str, role: str) -> None:
    """N2-N3: search + enrich people for a target, write to the Contacts tab."""
    typer.echo(f"TODO: find people at {company!r} for role {role!r}")


@app.command()
def draft() -> None:
    """N5: generate Gmail drafts for every checked (want_to_message) contact."""
    typer.echo("TODO: draft for checked contacts")


if __name__ == "__main__":
    app()
