"""Suspend/unsuspend commands."""

from __future__ import annotations

from pathlib import Path

import typer

from gsm.cli._shared import console, err_console, get_context
from gsm.cli.commands.users._app import users_app
from gsm.cli.commands.users._helpers import _resolve_user_targets

__all__ = ["users_suspend", "users_unsuspend"]


@users_app.command("suspend")
def users_suspend(
    ctx: typer.Context,
    file: Path | None = typer.Option(None, "--file", "-f", help="File with emails to suspend."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Suspend ALL users in domain."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview tanpa apply."),
) -> None:
    """Bulk suspend users (block login). Idempotent."""
    runtime = get_context(ctx)
    emails = _resolve_user_targets(runtime, file=file, domain=domain)
    if not emails:
        return

    if dry_run:
        console.print(f"[dim]--dry-run: would suspend {len(emails)} user(s)[/dim]")
        return

    from gsm.clients.google_admin import GoogleAdminError

    success = 0
    for email in emails:
        try:
            runtime.admin.suspend_user(email)
            success += 1
        except KeyboardInterrupt:
            console.print(
                f"\n[bold yellow]⚠️  Interrupted. Suspended {success}/{len(emails)} user(s).[/bold yellow]"
            )
            raise typer.Exit(code=130) from None
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Suspended {success}/{len(emails)} user(s).[/green]")


@users_app.command("unsuspend")
def users_unsuspend(
    ctx: typer.Context,
    file: Path | None = typer.Option(None, "--file", "-f", help="File with emails to unsuspend."),
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Unsuspend ALL users in domain."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview tanpa apply."),
) -> None:
    """Bulk unsuspend users (re-enable login). Idempotent."""
    runtime = get_context(ctx)
    emails = _resolve_user_targets(runtime, file=file, domain=domain)
    if not emails:
        return

    if dry_run:
        console.print(f"[dim]--dry-run: would unsuspend {len(emails)} user(s)[/dim]")
        return

    from gsm.clients.google_admin import GoogleAdminError

    success = 0
    for email in emails:
        try:
            runtime.admin.unsuspend_user(email)
            success += 1
        except KeyboardInterrupt:
            console.print(
                f"\n[bold yellow]⚠️  Interrupted. Unsuspended {success}/{len(emails)} user(s).[/bold yellow]"
            )
            raise typer.Exit(code=130) from None
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Unsuspended {success}/{len(emails)} user(s).[/green]")
