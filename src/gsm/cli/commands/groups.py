"""`gsm groups` subcommands: create, list, add-member, remove-member, members."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from gsm.cli._shared import err_console, get_context, read_lines

__all__ = [
    "groups_add_member",
    "groups_app",
    "groups_create",
    "groups_list",
    "groups_members",
    "groups_remove_member",
]

groups_app = typer.Typer(
    name="groups",
    help="Manage Google Workspace groups (mailing lists).",
    no_args_is_help=True,
)
console = Console()


@groups_app.command("create")
def groups_create(
    ctx: typer.Context,
    email: str = typer.Argument(..., help="Group email (e.g. all@domain.tech)."),
    name: str | None = typer.Option(None, "--name", "-n", help="Display name."),
    description: str = typer.Option("", "--desc", help="Group description."),
) -> None:
    """Create a group (mailing list). Idempotent."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        runtime.admin.create_group(email, name=name, description=description)
        console.print(f"[green][+][/green] Group created: {email}")
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=1) from e


@groups_app.command("list")
def groups_list(
    ctx: typer.Context,
    domain: str | None = typer.Option(None, "--domain", "-d", help="Filter by domain."),
) -> None:
    """List all groups."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        groups = runtime.admin.list_groups(domain=domain)
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=1) from e

    if not groups:
        console.print("[dim]No groups found.[/dim]")
        return

    table = Table(title=f"Groups ({len(groups)})")
    table.add_column("Email")
    table.add_column("Name")
    table.add_column("Members", justify="right")
    for g in groups:
        table.add_row(
            g.get("email", ""),
            g.get("name", ""),
            str(g.get("directMembersCount", "?")),
        )
    console.print(table)


@groups_app.command("add-member")
def groups_add_member(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group email."),
    member: str | None = typer.Option(None, "--member", "-m", help="Single member email."),
    file: Path | None = typer.Option(None, "--file", "-f", help="File with member emails."),
    role: str = typer.Option("MEMBER", "--role", help="Role: MEMBER, MANAGER, or OWNER."),
) -> None:
    """Add member(s) to a group."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    members: list[str] = []
    if file:
        members = read_lines(file)
    elif member:
        members = [member]
    else:
        err_console.print("[red][-][/red] Kasih --member atau --file.")
        raise typer.Exit(code=2)

    success = 0
    for m in members:
        try:
            runtime.admin.add_group_member(group, m, role=role.upper())
            success += 1
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {m}: {e}")
    console.print(f"[green]Added {success}/{len(members)} member(s) to {group}.[/green]")


@groups_app.command("remove-member")
def groups_remove_member(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group email."),
    member: str = typer.Argument(..., help="Member email to remove."),
) -> None:
    """Remove a member from a group."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        runtime.admin.remove_group_member(group, member)
        console.print(f"[green][+][/green] Removed {member} from {group}")
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=1) from e


@groups_app.command("members")
def groups_members(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group email."),
) -> None:
    """List members of a group."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        members = runtime.admin.list_group_members(group)
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=1) from e

    if not members:
        console.print(f"[dim]{group} has no members.[/dim]")
        return

    table = Table(title=f"Members of {group} ({len(members)})")
    table.add_column("Email")
    table.add_column("Role")
    table.add_column("Status")
    for m in members:
        table.add_row(m.get("email", ""), m.get("role", ""), m.get("status", ""))
    console.print(table)
