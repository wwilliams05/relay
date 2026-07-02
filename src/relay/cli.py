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

from . import config, flow, pipeline, resume
from .models import Contact, Job, Profile, Target
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
def discover(
    notes: str = typer.Option("", "--notes", "-n", help="Preferences not on your resume, e.g. 'Fall 2026 Co-Op, PM or BizOps'"),
    locations: Optional[str] = typer.Option(None, "--locations", "-l", help="Preferred locations, e.g. 'Los Angeles, New York, Remote'"),
    resume_pdf: Optional[str] = typer.Option(None, "--resume", help="Resume PDF (else uses saved profile)"),
) -> None:
    """N-1: scrape job boards for internships matching your resume + notes -> Jobs tab."""
    console.print(f"[dim]Jobs mode: {config.jobs_mode()} · tracker: {config.tracker_backend()}[/]")
    try:
        profile = flow.build_profile(resume_pdf, notes, locations)
        jobs = flow.discover_jobs(profile)
    except RuntimeError as err:
        _die(err)
        return
    _print_jobs(jobs, title="Discovered jobs (fit-ranked)")
    console.print(
        f"\n[green]{len(jobs)} jobs written[/] to the Jobs tab. "
        "[bold]Gate:[/] check [italic]pursue[/] on the ones you want, then run "
        "[bold]relay find-checked[/].")


@app.command()
def jobs() -> None:
    """Show the current Jobs tab."""
    rows = get_tracker().read_jobs()
    if not rows:
        console.print("[yellow]No jobs yet[/] — run [bold]relay discover[/] first.")
        return
    _print_jobs(rows, title="Jobs tab")


@app.command("find-checked")
def find_checked() -> None:
    """N2–N4 for every job you checked `pursue` on -> Contacts tab."""
    profile = _load_profile_or_warn()
    try:
        contacts, companies = flow.find_people_for_checked_jobs(profile)
    except RuntimeError as err:
        _die(err)
        return
    if not contacts:
        console.print("[yellow]No pursued jobs[/] — check [italic]pursue[/] in the Jobs tab first.")
        return
    _print_contacts(contacts, title=f"Contacts for {', '.join(sorted(set(companies)))}")
    console.print(
        f"\n[green]{len(contacts)} contacts written.[/] "
        "[bold]Gate:[/] check [italic]want_to_message[/] before drafting.")


@app.command()
def ui() -> None:
    """Launch the desktop launcher (import resume, notes, Run)."""
    from .gui import launch

    launch()


@app.command()
def log(
    name: str = typer.Argument(..., help="Contact name (or a unique part of it)"),
    responded: Optional[bool] = typer.Option(
        None, "--responded/--no-responded", help="Did they reply?"),
    notes: Optional[str] = typer.Option(None, "--notes", "-m", help="Tight chat summary (appends)"),
    next_step: Optional[str] = typer.Option(None, "--next-step", help="Concrete next step"),
    messaged: Optional[str] = typer.Option(
        None, "--messaged", help="Date you messaged them: YYYY-MM-DD or 'today'"),
) -> None:
    """N6: record a conversation outcome on a contact's row in the Contacts tab."""
    messaged_date = None
    if messaged:
        from datetime import date as _date

        try:
            messaged_date = _date.today() if messaged.lower() == "today" \
                else _date.fromisoformat(messaged)
        except ValueError:
            _die(ValueError(f"--messaged must be YYYY-MM-DD or 'today', got {messaged!r}"))
    try:
        contact = flow.log_chat(
            name, responded=responded, notes=notes, next_step=next_step,
            messaged_date=messaged_date)
    except RuntimeError as err:
        _die(err)
        return
    console.print(f"[green]Logged[/] — {contact.name} ({contact.company})")
    console.print(f"  messaged:  {contact.messaged_date or ''}")
    console.print(f"  responded: {'yes' if contact.responded else 'no'}")
    console.print(f"  notes:     {contact.chat_notes or ''}")
    console.print(f"  next step: {contact.next_step or ''}")


@app.command()
def projects() -> None:
    """Show the Projects tab (N7)."""
    try:
        rows = get_tracker().read_projects()
    except RuntimeError as err:
        _die(err)
        return
    if not rows:
        console.print("[yellow]No projects yet[/] — run [bold]/suggest-project[/] first.")
        return
    table = Table(title="Projects tab", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Company")
    table.add_column("For")
    table.add_column("Idea", overflow="fold")
    table.add_column("Skills")
    table.add_column("★", justify="center")
    table.add_column("PRD", justify="center")
    for i, p in enumerate(rows, 1):
        table.add_row(
            str(i), p.target_company, p.for_contact or "", p.project_idea,
            ", ".join(p.skills_shown), "☑" if p.interested else "☐",
            "✓" if p.prd_prompt else "",
        )
    console.print(table)
    console.print("[dim]Tick [italic]interested[/] in the tracker, then run "
                  "[bold]relay prd[/] to get the build prompt.[/]")


@app.command()
def prd() -> None:
    """N7: compose the ready-to-build PRD prompt for every `interested` project."""
    prof = _load_profile_or_warn()
    try:
        filled = flow.fill_prd_prompts(prof)
    except RuntimeError as err:
        _die(err)
        return
    if not filled:
        console.print(
            "[yellow]Nothing waiting[/] — tick [italic]interested[/] on a project in "
            "the tracker first (or every interested project already has its prompt).")
        return
    for p in filled:
        console.print(f"\n[bold green]{p.project_idea}[/] — {p.target_company}")
        console.print(p.prd_prompt)
    console.print(
        f"\n[green]{len(filled)} PRD prompt(s) saved[/] to the Projects tab. "
        "[bold]Gate:[/] you pick what to build; paste a prompt into an LLM to start.")


@app.command()
def draft() -> None:
    """N5: create rule-checked outreach drafts for every checked contact. Never sends."""
    prof = _load_profile_or_warn()
    console.print(
        f"[dim]Gmail mode: {config.gmail_mode()} · tracker: {config.tracker_backend()}[/]")
    try:
        run = flow.draft_outreach(prof)
    except RuntimeError as err:
        _die(err)
        return

    if run.nothing_checked:
        console.print(
            "[yellow]No contacts checked[/] — tick [italic]want_to_message[/] in the "
            "Contacts tab first (run [bold]relay find-checked[/] to populate it).")
        return
    for contact, ref in run.created:
        console.print(f"  [green]drafted[/] {contact.name} <{contact.email}> → {ref}")
    for contact in run.skipped_referrals:
        console.print(
            f"  [red]skipped[/] {contact.name} — uncleared referral. Confirm they're OK "
            "being named, tick [italic]referral_cleared[/], and re-run.")
    for contact in run.skipped_no_email:
        console.print(f"  [yellow]skipped[/] {contact.name} — no email (enrich first).")
    for contact, why in run.rule_violations:
        console.print(f"  [red]skipped[/] {contact.name} — {why}")
    if run.already_drafted:
        console.print(f"  [dim]{run.already_drafted} already drafted — left untouched.[/]")

    from .gmail import drafts_location

    if run.created:
        console.print(
            f"\n[green]{len(run.created)} draft(s) created[/] in {drafts_location()}. "
            "[bold]Gate:[/] edit and send each one yourself — Relay never sends.")


def _print_jobs(jobs: list[Job], title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Fit", justify="right")
    table.add_column("Company")
    table.add_column("Title", overflow="fold")
    table.add_column("Location")
    table.add_column("Source")
    table.add_column("Pursue", justify="center")
    for i, j in enumerate(jobs, 1):
        table.add_row(
            str(i), str(j.fit_score), j.company, j.title, j.location or "",
            j.source or "", "☑" if j.pursue else "☐",
        )
    console.print(table)


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
