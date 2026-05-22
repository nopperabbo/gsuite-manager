"""Audit command: inactive user detection."""

from __future__ import annotations

from pathlib import Path

import typer

from gsm.cli._shared import console, err_console, get_context
from gsm.cli.commands.users._app import users_app

__all__ = ["users_audit"]


@users_app.command("audit")
def users_audit(
    ctx: typer.Context,
    inactive_days: int = typer.Option(
        30, "--inactive-days", "-d", help="Threshold hari tidak login."
    ),
    domain: str | None = typer.Option(None, "--domain", help="Filter by domain."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Save inactive emails ke file."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List users yang tidak login > N hari. Berguna untuk cleanup dead accounts."""
    from datetime import UTC, datetime, timedelta

    from rich.table import Table

    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        ws_users = runtime.admin.list_users(domain=domain)
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {e}")
        raise typer.Exit(code=2) from e

    now = datetime.now(UTC)
    threshold = now - timedelta(days=inactive_days)
    inactive: list[tuple[str, str, int]] = []
    active = 0

    for u in ws_users:
        email = u.get("primaryEmail", "")
        last_login = u.get("lastLoginTime", "")
        if not last_login or last_login == "1970-01-01T00:00:00.000Z":
            inactive.append((email, "never", 9999))
            continue
        try:
            login_dt = datetime.fromisoformat(last_login.replace("Z", "+00:00"))
            days_ago = (now - login_dt).days
            if login_dt < threshold:
                inactive.append((email, last_login[:10], days_ago))
            else:
                active += 1
        except ValueError:
            inactive.append((email, "parse_error", 9999))

    if json_output:
        import json

        data = {
            "active": active,
            "inactive_count": len(inactive),
            "threshold_days": inactive_days,
            "inactive": [
                {"email": email, "last_login": last, "days_ago": days if days < 9999 else None}
                for email, last, days in sorted(inactive, key=lambda x: -x[2])
            ],
        }
        typer.echo(json.dumps(data, indent=2))
        return

    if inactive:
        table = Table(title=f"Inactive users (>{inactive_days} days, {len(inactive)} found)")
        table.add_column("Email")
        table.add_column("Last Login")
        table.add_column("Days Ago", justify="right")
        for email, last, days in sorted(inactive, key=lambda x: -x[2])[:100]:
            table.add_row(email, last, str(days) if days < 9999 else "never")
        console.print(table)
    else:
        console.print(
            f"[green][+] All {active} users logged in within {inactive_days} days.[/green]"
        )

    console.print(f"\n[green]Active: {active}[/green]  [yellow]Inactive: {len(inactive)}[/yellow]")

    if output and inactive:
        lines = [email for email, _, _ in inactive]
        output.write_text("\n".join(lines) + "\n")
        console.print(f"[green][+][/green] Inactive emails saved to [cyan]{output}[/cyan]")
