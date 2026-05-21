"""Alias commands: alias-add, alias-list, alias-remove."""

from __future__ import annotations

import typer

from gsm.cli._shared import console, err_console, get_context
from gsm.cli.commands.users._app import users_app

__all__ = ["users_alias_add", "users_alias_list", "users_alias_remove"]


@users_app.command("alias-add")
def users_alias_add(
    ctx: typer.Context,
    email: str = typer.Argument(..., help="User email (target)."),
    alias: str = typer.Argument(..., help="Alias email to add."),
) -> None:
    """Add email alias to a user (e.g. info@domain -> user@domain)."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        runtime.admin.add_alias(email, alias)
        console.print(f"[green][+][/green] Alias {alias} \u2192 {email}")
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=1) from e


@users_app.command("alias-list")
def users_alias_list(
    ctx: typer.Context,
    email: str = typer.Argument(..., help="User email to list aliases for."),
) -> None:
    """List all aliases for a user."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        aliases = runtime.admin.list_aliases(email)
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=1) from e
    if not aliases:
        console.print(f"[dim]{email} has no aliases.[/dim]")
        return
    for a in aliases:
        console.print(f"  \u2022 {a} \u2192 {email}")


@users_app.command("alias-remove")
def users_alias_remove(
    ctx: typer.Context,
    email: str = typer.Argument(..., help="User email (owner)."),
    alias: str = typer.Argument(..., help="Alias to remove."),
) -> None:
    """Remove email alias from a user."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        runtime.admin.remove_alias(email, alias)
        console.print(f"[green][+][/green] Removed alias {alias}")
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=1) from e
