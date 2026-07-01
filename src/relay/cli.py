"""Thin CLI. The real orchestration lives in .claude/commands/ (Claude Code skills);
this exposes the deterministic helpers so skills (and you) can call them directly.

Stages wired for M1 (N0–N4):
    relay profile <resume.pdf>            parse resume -> Profile (N0)
    relay target "SpaceX" "Business Ops"  define a target -> Targets tab (N1)
    relay find "SpaceX" "Business Ops"    search + enrich + rank -> Contacts tab (N2–N4)
    relay contacts                        show the current Contacts tab
"""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import config, pipeline, resume
from .models import Contact, Profile, Target
from .sheets import get_tracker

# Windows consoles default to cp1252, which chokes on the checkbox/em-dash glyphs we
# print. Force UTF-8 so output renders the same everywhere.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

app = typer.Typer(help="Relay — networking outreach orchestrator", no_args_is_help=True)
console = Console()


def _die(err: Exception) -> None:
    """Print a clean one-line error for expected config problems and exit non-zero."""
    console.print(f"[red]Error:[/] {err}")
    raise typer.Exit(1)


def _load_profile_or_warn() -> Profile:
    profile = resume.load_profile()
    if profile is None:
        console.print(
            "[yellow]No saved profile[/] — run [bold]relay profile <resume.pdf>[/] first "
            "so alumni matching works. Continuing with an empty profile.")
        return Profile(name="(unknown)")
    return profile


@app.command()
def profile(
    resume_pdf: str = typer.Argument(..., help="Path to your resume PDF"),
) -> None:
    """N0: parse a resume PDF into a Profile and cache it as profile.json."""
    prof = resume.parse_resume(resume_pdf)
    out = resume.save_profile(prof)
    console.print(f"[green]Parsed profile[/] -> {out}")
    console.print(f"  name:    {prof.name}")
    console.print(f"  schools: {', '.join(prof.schools) or '(none detected)'}")
    console.print(
        "[dim]Tip: schools/roles/skills are heuristic — edit profile.json or let "
        "/find-people refine them.[/]")


@app.command()
def target(
    company: str,
    role: str,
    jd_url: Optional[str] = typer.Option(None, "--jd", help="Job description URL"),
) -> None:
    """N1: define a company + role target and write it to the Targets tab."""
    tgt = Target(
        company=company, role=role, jd_url=jd_url,
        similar_titles=pipeline.default_similar_titles(role),
    )
    try:
        get_tracker().upsert_target(tgt)
    except RuntimeError as err:
        _die(err)
    console.print(f"[green]Target saved[/] — {company} / {role}")
    console.print(f"  similar titles: {', '.join(tgt.similar_titles)}")


@app.command()
def find(
    company: str,
    role: str,
    jd_url: Optional[str] = typer.Option(None, "--jd", help="Job description URL"),
    per_page: int = typer.Option(25, "--per-page", help="Max people to pull from Apollo"),
    no_enrich: bool = typer.Option(False, "--no-enrich", help="Skip email enrichment (saves credits)"),
) -> None:
    """N2–N4: search + enrich + rank people for a target -> Contacts tab (unchecked)."""
    prof = _load_profile_or_warn()
    tgt = Target(
        company=company, role=role, jd_url=jd_url,
        similar_titles=pipeline.default_similar_titles(role),
    )
    console.print(
        f"[dim]Apollo mode: {config.apollo_mode()} · tracker: {config.tracker_backend()}[/]")

    try:
        tracker = get_tracker()
        tracker.upsert_target(tgt)
        contacts = pipeline.find_people(tgt, prof, per_page=per_page, enrich=not no_enrich)
        tracker.write_contacts(contacts)
    except RuntimeError as err:
        _die(err)

    _print_contacts(contacts, title=f"{company} — {role}  (ranked, §5)")
    nudge = pipeline.mutuals_nudge(contacts)
    if nudge:
        console.print("\n[bold]Manual step[/] — eyeball these on LinkedIn for mutuals (PRD §7):")
        for name in nudge:
            console.print(f"  • {name}")
    console.print(
        f"\n[green]{len(contacts)} contacts written[/] to the Contacts tab. "
        "[bold]Gate:[/] check [italic]want_to_message[/] yourself before drafting.")


@app.command()
def contacts() -> None:
    """Show the current Contacts tab."""
    try:
        rows = get_tracker().read_contacts()
    except RuntimeError as err:
        _die(err)
        return
    if not rows:
        console.print("[yellow]No contacts yet[/] — run [bold]relay find ...[/] first.")
        return
    _print_contacts(rows, title="Contacts tab")


@app.command()
def draft() -> None:
    """N5 (M2): generate Gmail drafts for every checked (want_to_message) contact."""
    console.print("[yellow]N5 lands in M2[/] — draft generation not wired yet.")


def _print_contacts(contacts: list[Contact], title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name")
    table.add_column("Title", overflow="fold")
    table.add_column("Why")
    table.add_column("School")
    table.add_column("Email")
    table.add_column("Status")
    table.add_column("✓", justify="center")
    for i, c in enumerate(contacts, 1):
        table.add_row(
            str(i), c.name, c.title or "", c.why.value, c.school_match or "",
            str(c.email or ""), c.email_status.value,
            "☑" if c.want_to_message else "☐",
        )
    console.print(table)


if __name__ == "__main__":
    app()
