from typing import Optional

import typer

from .analyze import analyze_ticket
from .config import install_config, load_config
from .fetch import fetch_ticket
from .investigate import investigate_ticket
from .pipeline import Stage, run_pipeline
from .plan import plan_ticket

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def _main() -> None:
    """Jira ticket analysis tool."""


@app.command()
def install() -> None:
    """Create config file from example template."""
    install_config()


@app.command()
def run(
    ticket_id: str = typer.Argument(..., help="Jira ticket ID, e.g. JIRA-123"),
    force: bool = typer.Option(False, "--force", help="Re-run all stages even if outputs exist."),
    from_stage: Optional[Stage] = typer.Option(
        None, "--from", help="Re-run starting at the named stage."
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model for this run"),
) -> None:
    """Run fetch -> analyze -> investigate -> plan in sequence for a single ticket."""
    if force and from_stage:
        print("Error: --force and --from are mutually exclusive.", file=typer.sys.stderr)
        raise typer.Exit(code=1)

    run_pipeline(ticket_id, force=force, from_stage=from_stage, model_override=model)


@app.command()
def fetch(
    ticket_id: str = typer.Argument(..., help="Jira ticket ID, e.g. JIRA-123"),
) -> None:
    """Fetch Jira ticket data and attachments, write raw JSON. Edit the output before running analyze."""
    config = load_config()
    raw_path, att_count = fetch_ticket(ticket_id, config)
    print(f"Fetched: {raw_path} ({att_count} attachment(s) downloaded)")


@app.command()
def analyze(
    ticket_id: str = typer.Argument(..., help="Jira ticket ID, e.g. JIRA-123"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model for this run"),
) -> None:
    """Run LLM triage on raw JSON from fetch, produce a parsed summary."""
    config = load_config()
    analyze_ticket(ticket_id, config, model)


@app.command()
def investigate(
    ticket_id: str = typer.Argument(..., help="Jira ticket ID, e.g. JIRA-123"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model for this run"),
) -> None:
    """Compare the ticket triage against the codebase and produce an investigation report."""
    config = load_config()
    investigate_ticket(ticket_id, config, model)


@app.command()
def plan(
    ticket_id: str = typer.Argument(..., help="Jira ticket ID, e.g. JIRA-123"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model for this run"),
) -> None:
    """Decompose an investigation report into a master plan and atomic tasks."""
    config = load_config()
    plan_ticket(ticket_id, config, model)
