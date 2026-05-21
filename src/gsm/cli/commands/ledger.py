"""`gsm ledger` commands - manage local state (archive, stats)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from gsm.cli._shared import get_context

__all__ = ["ledger_app", "ledger_archive", "ledger_stats"]

ledger_app = typer.Typer(name="ledger", no_args_is_help=True, help="Manage the local ledger.")
console = Console()


@ledger_app.command("stats")
def ledger_stats(ctx: typer.Context) -> None:
    """Show counts of records by status."""
    runtime = get_context(ctx)
    stats = runtime.ledger.stats()
    if not stats:
        typer.echo("(ledger is empty)")
        return
    table = Table(title="Ledger stats")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for key, value in sorted(stats.items()):
        table.add_row(key, str(value))
    console.print(table)


@ledger_app.command("archive")
def ledger_archive(
    ctx: typer.Context,
    older_than_days: int = typer.Option(
        90,
        "--older-than-days",
        min=1,
        help="Move records last updated before this many days ago.",
    ),
    archive_to: str | None = typer.Option(
        None,
        "--to",
        help="Archive file path (default: <ledger>.archive.json next to ledger).",
    ),
) -> None:
    """Move stale ledger entries into an archive file (idempotent, atomic)."""
    runtime = get_context(ctx)
    cutoff = datetime.now() - timedelta(days=older_than_days)
    target = Path(archive_to) if archive_to else runtime.ledger.path.with_name(
        runtime.ledger.path.name + ".archive.json"
    )
    moved = runtime.ledger.archive(before=cutoff, archive_path=target)
    typer.echo(
        f"archived {moved} record(s) older than {older_than_days}d -> {target}"
    )
