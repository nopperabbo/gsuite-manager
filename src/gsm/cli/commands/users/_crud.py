"""CRUD commands: add, list, reset-password, move, delete, update."""

from __future__ import annotations

from pathlib import Path

import typer

from gsm.cli._shared import (
    batch_progress,
    console,
    err_console,
    get_context,
    render_interrupted_summary,
    render_results,
)
from gsm.cli.commands.users._app import users_app
from gsm.cli.commands.users._helpers import _assign_licenses, _resolve_user_targets
from gsm.models.results import ResultKind
from gsm.models.user import UserStatus
from gsm.workflows.user_bulk_create import create_users, parse_akun_file

__all__ = [
    "users_add",
    "users_delete",
    "users_list",
    "users_move",
    "users_reset_password",
    "users_update",
]


@users_app.command("add")
def users_add(
    ctx: typer.Context,
    file: Path = typer.Option(
        Path("akun.txt"),
        "--file",
        "-f",
        help="Path to akun.txt file (format: email|password|kode per line). "
        "Resolved relative to CWD.",
    ),
    license: str | None = typer.Option(
        None,
        "--license",
        "-L",
        help="Assign license after create: 'education', 'gmail-only', 'education-standard', 'education-plus'.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview tanpa apply."),
) -> None:
    """Bulk-create Workspace users from akun.txt."""
    accounts = parse_akun_file(file)
    if not accounts:
        typer.echo(f"No valid accounts parsed from {file}")
        raise typer.Exit(code=1)

    if dry_run:
        console.print(f"[dim]--dry-run: would create {len(accounts)} user(s) from {file}[/dim]")
        return

    runtime = get_context(ctx)
    with batch_progress(f"Creating {len(accounts)} user(s)", len(accounts)) as on_progress:
        results = create_users(
            accounts,
            settings=runtime.settings,
            ledger=runtime.ledger,
            admin=runtime.admin,
            on_progress=on_progress,
        )
    if len(results) < len(accounts):
        render_interrupted_summary(results, len(accounts))
        raise typer.Exit(code=130)
    render_results(results, title=f"Creating {len(accounts)} user(s)")

    if license and any(r.kind is ResultKind.SUCCESS for r in results):
        _assign_licenses(runtime, results, license)

    if any(r.kind is ResultKind.FAILED for r in results):
        raise typer.Exit(code=1)


@users_app.command("list")
def users_list(
    ctx: typer.Context,
    domain: str | None = typer.Option(None, "--domain", help="Filter by domain (email suffix)."),
    status: str | None = typer.Option(
        None, "--status", help="Filter by status: PENDING, CREATED, FAILED."
    ),
) -> None:
    """List users tracked in the ledger, optionally filtered by domain/status."""
    from rich.table import Table

    runtime = get_context(ctx)
    status_filter = None
    if status is not None:
        try:
            status_filter = UserStatus(status.lower())
        except ValueError as e:
            raise typer.BadParameter(
                f"unknown status: {status}. Valid: {', '.join(s.value for s in UserStatus)}"
            ) from e

    records = runtime.ledger.list_users(domain=domain)
    if status_filter is not None:
        records = [r for r in records if r.status is status_filter]

    if not records:
        typer.echo("(no users in ledger)")
        return

    table = Table(title=f"Users ({len(records)})")
    table.add_column("Email")
    table.add_column("Status")
    table.add_column("Last Updated")
    table.add_column("Last Error")

    for r in records:
        table.add_row(
            r.email,
            r.status.value,
            r.last_updated.strftime("%Y-%m-%d %H:%M"),
            (r.last_error or "")[:60],
        )
    console.print(table)


@users_app.command("reset-password")
def users_reset_password(
    ctx: typer.Context,
    domain: str | None = typer.Option(None, "--domain", "-d", help="Filter users by domain."),
    file: Path | None = typer.Option(None, "--file", "-f", help="File with emails (one per line)."),
    same_password: str | None = typer.Option(None, "--same-password", help="Set same password for all users."),
    random: bool = typer.Option(False, "--random", help="Generate random password per user."),
    length: int = typer.Option(16, "--length", help="Random password length."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write email|new_password ke file."),
    force_change: bool = typer.Option(False, "--force-change", help="Force user change password at next login."),
) -> None:
    """Bulk reset password: --same-password 'X' atau --random."""
    import secrets
    import string

    if not same_password and not random:
        err_console.print(
            "[red][-][/red] Harus pilih salah satu: --same-password 'X' atau --random"
        )
        raise typer.Exit(code=2)

    runtime = get_context(ctx)

    emails: list[str] = []
    if file:
        from gsm.cli._shared import read_lines
        emails = read_lines(file)
    elif domain:
        from gsm.clients.google_admin import GoogleAdminError
        try:
            ws_users = runtime.admin.list_users(domain=domain)
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {e}")
            raise typer.Exit(code=2) from e
        emails = [u["primaryEmail"] for u in ws_users if u.get("primaryEmail")]
    else:
        err_console.print(
            "[red][-][/red] Harus kasih --domain atau --file (target users)."
        )
        raise typer.Exit(code=2)

    if not emails:
        console.print("[yellow][!][/yellow] Gak ada user yang match.")
        return

    console.print(f"[cyan]Resetting password for {len(emails)} user(s)...[/cyan]")

    alphabet = string.ascii_letters + string.digits + "!@#$%"
    results: list[tuple[str, str, bool]] = []

    from gsm.clients.google_admin import GoogleAdminError

    for email in emails:
        pw = same_password if same_password else "".join(
            secrets.choice(alphabet) for _ in range(length)
        )
        try:
            runtime.admin.update_password(
                email=email, password=pw, change_at_next_login=force_change
            )
            results.append((email, pw, True))
        except GoogleAdminError as e:
            results.append((email, "", False))
            err_console.print(f"[red][-][/red] {email}: {e}")

    success = sum(1 for _, _, ok in results if ok)
    failed = len(results) - success
    console.print(
        f"\n[green]success={success}[/green]  [red]failed={failed}[/red]"
    )

    if output and success > 0:
        lines = [f"{email} | {pw}" for email, pw, ok in results if ok]
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        output.chmod(0o600)
        console.print(f"[green][+][/green] Credentials written to [cyan]{output}[/cyan] (mode 0600)")
    elif random and not output and success > 0:
        console.print(
            "\n[yellow][!][/yellow] Random passwords generated tapi --output gak di-set.\n"
            "    Password gak bisa di-recover! Tambahin --output <file> next time."
        )
        from rich.table import Table
        t = Table(title="Generated passwords (SAVE THIS!)")
        t.add_column("Email")
        t.add_column("Password")
        for email, pw, ok in results:
            if ok:
                t.add_row(email, pw)
        console.print(t)


@users_app.command("move")
def users_move(
    ctx: typer.Context,
    ou: str = typer.Option(..., "--ou", help="Target Organizational Unit path (e.g. '/Sales')."),
    file: Path | None = typer.Option(None, "--file", "-f", help="File with emails to move."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Move ALL users in domain."),
) -> None:
    """Move users to an Organizational Unit (OU)."""
    runtime = get_context(ctx)
    emails = _resolve_user_targets(runtime, file=file, domain=domain)
    if not emails:
        return

    from gsm.clients.google_admin import GoogleAdminError

    success = 0
    for email in emails:
        try:
            runtime.admin.move_user_to_ou(email, ou)
            success += 1
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Moved {success}/{len(emails)} user(s) to OU '{ou}'.[/green]")


@users_app.command("delete")
def users_delete(
    ctx: typer.Context,
    file: Path | None = typer.Option(None, "--file", "-f", help="File with emails to delete."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Delete ALL users in domain."),
    confirm: bool = typer.Option(False, "--yes", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview tanpa apply."),
) -> None:
    """Bulk delete users (PERMANENT - 30 day recovery window in Google)."""
    from rich.prompt import Confirm

    runtime = get_context(ctx)
    emails = _resolve_user_targets(runtime, file=file, domain=domain)
    if not emails:
        return

    if dry_run:
        console.print(f"[dim]--dry-run: would delete {len(emails)} user(s)[/dim]")
        return

    console.print(
        f"[bold red]⚠️  DELETING {len(emails)} user(s). This is PERMANENT.[/bold red]\n"
        "[dim]Google keeps deleted users for 30 days (recoverable via Admin Console).[/dim]"
    )
    if not confirm and not Confirm.ask("Yakin mau delete?", default=False):
        console.print("[dim]Cancelled.[/dim]")
        return

    from gsm.clients.google_admin import GoogleAdminError

    success = 0
    for email in emails:
        try:
            runtime.admin.delete_user(email)
            success += 1
        except KeyboardInterrupt:
            console.print(
                f"\n[bold yellow]⚠️  Interrupted. Deleted {success}/{len(emails)} user(s).[/bold yellow]"
            )
            raise typer.Exit(code=130) from None
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Deleted {success}/{len(emails)} user(s).[/green]")


@users_app.command("update")
def users_update(
    ctx: typer.Context,
    file: Path = typer.Option(..., "--file", "-f", help="CSV file: email,field,value (one change per line)."),
) -> None:
    """Bulk update user info from CSV (name, department, title, phone).

    CSV format (no header):
      user@domain.tech,first_name,John
      user@domain.tech,last_name,Doe
      user@domain.tech,department,Engineering
      user@domain.tech,title,Senior Dev
      user@domain.tech,phone,+628123456789
    """
    from gsm.clients.google_admin import GoogleAdminError

    if not file.exists():
        err_console.print(f"[red][-][/red] File not found: {file}")
        raise typer.Exit(code=2)

    runtime = get_context(ctx)
    updates: dict[str, dict[str, str]] = {}
    with file.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",", 2)]
            if len(parts) < 3:
                continue
            email, field, value = parts
            updates.setdefault(email, {})[field] = value

    if not updates:
        console.print("[yellow]No valid updates in file.[/yellow]")
        return

    success = 0
    for email, fields in updates.items():
        try:
            runtime.admin.update_user(email, **fields)
            success += 1
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Updated {success}/{len(updates)} user(s).[/green]")
