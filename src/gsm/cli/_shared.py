"""Shared CLI helpers: dependency wiring, input parsing, output rendering."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from gsm.clients.cloudflare import CloudflareClient
from gsm.clients.google_admin import GoogleAdminClient
from gsm.clients.google_verify import GoogleVerifyClient
from gsm.core.auth import OAuthDesktopAuth
from gsm.core.config import Settings, load_settings
from gsm.core.logging import configure_logging
from gsm.models.results import ItemResult, ResultKind
from gsm.state.ledger import Ledger

__all__ = [
    "Context",
    "batch_progress",
    "console",
    "err_console",
    "get_context",
    "read_lines",
    "render_interrupted_summary",
    "render_results",
]

console = Console()
err_console = Console(stderr=True)


class Context:
    """Shared CLI runtime state, lazily wired from settings."""

    __slots__ = ("_admin", "_auth", "_cf", "_ledger", "_verify", "settings")

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ledger: Ledger | None = None
        self._auth: OAuthDesktopAuth | None = None
        self._cf: CloudflareClient | None = None
        self._admin: GoogleAdminClient | None = None
        self._verify: GoogleVerifyClient | None = None

    @property
    def ledger(self) -> Ledger:
        if self._ledger is None:
            self._ledger = Ledger(self.settings.ledger_path)
        return self._ledger

    @property
    def auth(self) -> OAuthDesktopAuth:
        if self._auth is None:
            self._auth = OAuthDesktopAuth(self.settings)
        return self._auth

    @property
    def cf(self) -> CloudflareClient:
        if self._cf is None:
            self._cf = CloudflareClient(self.settings)
        return self._cf

    @property
    def admin(self) -> GoogleAdminClient:
        if self._admin is None:
            self._admin = GoogleAdminClient(self.auth)
        return self._admin

    @property
    def verify(self) -> GoogleVerifyClient:
        if self._verify is None:
            self._verify = GoogleVerifyClient(self.auth)
        return self._verify


def get_context(ctx: typer.Context) -> Context:
    """Retrieve shared Context from Typer ctx, building it on first call."""
    obj = ctx.obj
    if not isinstance(obj, Context):
        try:
            settings = load_settings()
        except ValidationError as e:
            err_console.print(
                "[red][-][/red] Configuration is incomplete or invalid.\n"
                "Run [cyan]gsm init[/cyan] to scaffold .env, then edit it and try again.\n"
                "Or run [cyan]gsm doctor[/cyan] to see exactly what is missing.\n"
            )
            for error in e.errors():
                loc = ".".join(str(p) for p in error["loc"])
                err_console.print(f"  [red]{loc}[/red]: {error['msg']}")
            raise typer.Exit(code=2) from e
        configure_logging(settings)
        obj = Context(settings)
        ctx.obj = obj
    return obj


def read_lines(path: Path) -> list[str]:
    """Read a text file (one item per line, blanks/comments ignored)."""
    if not path.exists():
        raise typer.BadParameter(f"file not found: {path}")
    items: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            items.append(line)
    if not items:
        raise typer.BadParameter(f"file is empty or only comments: {path}")
    return items


_KIND_STYLE = {
    ResultKind.SUCCESS: "green",
    ResultKind.SKIPPED: "cyan",
    ResultKind.PARTIAL: "yellow",
    ResultKind.FAILED: "red",
}


def render_results(results: Iterable[ItemResult], *, title: str) -> None:
    """Render workflow results as a Rich table."""
    table = Table(title=title, show_lines=False)
    table.add_column("Status", no_wrap=True)
    table.add_column("Identifier")
    table.add_column("Message")

    success = skipped = partial = failed = 0
    for item in results:
        style = _KIND_STYLE.get(item.kind, "white")
        table.add_row(
            f"[{style}]{item.kind.value}[/{style}]",
            item.identifier,
            item.message,
        )
        if item.kind is ResultKind.SUCCESS:
            success += 1
        elif item.kind is ResultKind.SKIPPED:
            skipped += 1
        elif item.kind is ResultKind.PARTIAL:
            partial += 1
        elif item.kind is ResultKind.FAILED:
            failed += 1

    console.print(table)
    console.print(
        f"[green]success[/green]={success}  "
        f"[cyan]skipped[/cyan]={skipped}  "
        f"[yellow]partial[/yellow]={partial}  "
        f"[red]failed[/red]={failed}"
    )


def render_interrupted_summary(results: list[ItemResult], total: int) -> None:
    """Print partial results summary after SIGINT interruption."""
    from gsm.models.results import ResultKind

    completed = len(results)
    success = sum(1 for r in results if r.kind is ResultKind.SUCCESS)
    failed = sum(1 for r in results if r.kind is ResultKind.FAILED)
    console.print(
        f"\n[bold yellow]⚠️  Interrupted (Ctrl+C). "
        f"Completed {completed}/{total}:[/bold yellow]  "
        f"[green]success[/green]={success}  "
        f"[red]failed[/red]={failed}  "
        f"[dim]remaining={total - completed}[/dim]"
    )


from contextlib import contextmanager  # noqa: E402

from rich.progress import (  # noqa: E402
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


@contextmanager
def batch_progress(
    label: str, total: int
) -> Iterator[Callable[[int, int, str, Any], None]]:
    """Context manager that yields an `on_progress(idx, total, ident, result)` callback.

    Renders a Rich progress bar with ETA, item counter, and last-item status.
    Disabled when total <= 1 (single item gets simpler output via render_results).
    """
    if total <= 1:
        yield lambda *_, **__: None
        return

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TextColumn("ETA"),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.fields[current]}"),
        console=console,
        transient=False,
    )

    with progress:
        task_id = progress.add_task(label, total=total, current="...")

        def callback(idx: int, total_: int, ident: str, result: Any) -> None:
            from gsm.models.results import ResultKind

            kind = result.kind
            color = {
                ResultKind.SUCCESS: "green",
                ResultKind.SKIPPED: "cyan",
                ResultKind.PARTIAL: "yellow",
                ResultKind.FAILED: "red",
            }.get(kind, "white")
            tag = kind.value
            progress.update(
                task_id,
                advance=1,
                current=f"[{color}]{tag}[/{color}] {ident}",
            )

        yield callback
