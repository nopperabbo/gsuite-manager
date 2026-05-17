"""`gsm users` subcommands: add, list, gen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from pydantic import SecretStr

from gsm.cli._shared import batch_progress, console, err_console, get_context, render_results
from gsm.clients.username_generator import (
    DEFAULT_COLLISION_FALLBACK,
    DEFAULT_PASSWORD_LENGTH,
    DEFAULT_PATTERN,
    GeneratedAccount,
    GeneratorError,
    generate_accounts,
)
from gsm.models.results import ResultKind
from gsm.models.user import AccountSpec, UserStatus
from gsm.workflows.user_bulk_create import create_users, parse_akun_file

users_app = typer.Typer(
    name="users",
    help="Manage Workspace users: bulk create, inspect.",
    no_args_is_help=True,
)


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
) -> None:
    """Bulk-create Workspace users from akun.txt."""
    accounts = parse_akun_file(file)
    if not accounts:
        typer.echo(f"No valid accounts parsed from {file}")
        raise typer.Exit(code=1)

    runtime = get_context(ctx)
    with batch_progress(f"Creating {len(accounts)} user(s)", len(accounts)) as on_progress:
        results = create_users(
            accounts,
            settings=runtime.settings,
            ledger=runtime.ledger,
            admin=runtime.admin,
            on_progress=on_progress,
        )
    render_results(results, title=f"Creating {len(accounts)} user(s)")
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


@users_app.command("gen")
def users_gen(
    ctx: typer.Context,
    domain: str = typer.Option(
        ...,
        "--domain",
        "-d",
        help="Target domain untuk akun yang di-generate (mis. bunhe.tech).",
    ),
    count: int = typer.Option(
        ...,
        "--count",
        "-n",
        min=1,
        max=10_000,
        help="Jumlah akun yang ingin di-generate.",
    ),
    locale: str = typer.Option(
        "id_ID",
        "--locale",
        "-l",
        help="Locale Faker untuk nama: id_ID, en_US, dll. Default: id_ID.",
    ),
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=(
            "Format email. Token: {first}, {last}, {first_initial}, "
            "{last_initial}, {n}, {domain}. "
            f"Default: '{DEFAULT_PATTERN}'."
        ),
    ),
    collision_fallback: str = typer.Option(
        DEFAULT_COLLISION_FALLBACK,
        "--collision-fallback",
        help=(
            "Pattern alternatif kalo email pertama collision. "
            f"Default: '{DEFAULT_COLLISION_FALLBACK}'."
        ),
    ),
    password_length: int = typer.Option(
        DEFAULT_PASSWORD_LENGTH,
        "--password-length",
        min=8,
        max=64,
        help=f"Panjang password random (min 8). Default: {DEFAULT_PASSWORD_LENGTH}.",
    ),
    fixed_password: str | None = typer.Option(
        None,
        "--fixed-password",
        help=(
            "Pakai password yang sama untuk semua akun (TESTING ONLY). Override --password-length."
        ),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Tulis ke file (format: email|password|kode). Compatible dengan `gsm users add --file`."
        ),
    ),
    apply_now: bool = typer.Option(
        False,
        "--apply",
        help=(
            "Langsung create user ke Workspace setelah generate. "
            "Tanpa flag ini, hanya preview / tulis ke file."
        ),
    ),
    license: str | None = typer.Option(
        None,
        "--license",
        "-L",
        help=(
            "Assign license setelah create. "
            "Options: 'education' (full), 'gmail-only' (Fundamentals), "
            "atau SKU ID custom."
        ),
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        help="Seed Faker untuk output reproducible (testing).",
    ),
) -> None:
    """Generate akun otomatis pakai Faker (locale-aware), avoid collision."""
    runtime = get_context(ctx)

    existing = [u.email for u in runtime.ledger.list_users(domain=domain.lower())]
    if existing:
        console.print(
            f"[dim]Skip {len(existing)} email yang udah ada di ledger untuk domain {domain}.[/dim]"
        )

    try:
        accounts = generate_accounts(
            domain=domain,
            count=count,
            locale=locale,
            pattern=pattern,
            collision_fallback=collision_fallback,
            password_length=password_length,
            fixed_password=fixed_password,
            existing_emails=existing,
            seed=seed,
        )
    except GeneratorError as e:
        err_console.print(f"[red][-][/red] Generator error: {e}")
        raise typer.Exit(code=2) from e

    _render_preview(accounts, redact_password=output is None and not apply_now)

    if output is not None:
        _write_akun_file(output, accounts)
        console.print(f"[green][+][/green] {len(accounts)} akun ditulis ke [cyan]{output}[/cyan]")
        console.print(f"[dim]Run: gsm users add --file {output}[/dim]")

    if apply_now:
        specs = [
            AccountSpec(
                email=a.email,
                password=SecretStr(a.password),
                first_name=a.first_name,
                last_name=a.last_name,
            )
            for a in accounts
        ]
        with batch_progress(f"Creating {len(specs)} user(s)", len(specs)) as on_progress:
            results = create_users(
                specs,
                settings=runtime.settings,
                ledger=runtime.ledger,
                admin=runtime.admin,
                on_progress=on_progress,
            )
        render_results(results, title=f"Creating {len(specs)} user(s)")

        if license and any(r.kind is ResultKind.SUCCESS for r in results):
            _assign_licenses(runtime, results, license)

        if any(r.kind is ResultKind.FAILED for r in results):
            raise typer.Exit(code=1)


def _render_preview(accounts: list[GeneratedAccount], *, redact_password: bool) -> None:
    """Print a preview table of generated accounts."""
    from rich.table import Table

    table = Table(title=f"Generated {len(accounts)} accounts")
    table.add_column("#", justify="right", width=4)
    table.add_column("Email")
    table.add_column("Password")
    table.add_column("First Name")
    table.add_column("Last Name")

    for i, a in enumerate(accounts, 1):
        password_display = "******" if redact_password else a.password
        table.add_row(
            str(i),
            a.email,
            password_display,
            a.first_name,
            a.last_name,
        )
    console.print(table)
    if redact_password:
        console.print(
            "[dim]Password disembunyikan. Pakai --output FILE atau --apply "
            "untuk pakai password asli.[/dim]"
        )


def _write_akun_file(path: Path, accounts: list[GeneratedAccount]) -> None:
    """Write akun.txt-compatible file with mode 0600 for safety."""
    import contextlib

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [a.to_akun_line() for a in accounts]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Best-effort restrict perms; on non-POSIX (Windows) chmod is a no-op-ish.
    with contextlib.suppress(OSError):
        path.chmod(0o600)


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


@users_app.command("suspend")
def users_suspend(
    ctx: typer.Context,
    file: Path | None = typer.Option(None, "--file", "-f", help="File with emails to suspend."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Suspend ALL users in domain."),
) -> None:
    """Bulk suspend users (block login). Idempotent."""
    runtime = get_context(ctx)
    emails = _resolve_user_targets(runtime, file=file, domain=domain)
    if not emails:
        return

    from gsm.clients.google_admin import GoogleAdminError

    success = 0
    for email in emails:
        try:
            runtime.admin.suspend_user(email)
            success += 1
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Suspended {success}/{len(emails)} user(s).[/green]")


@users_app.command("unsuspend")
def users_unsuspend(
    ctx: typer.Context,
    file: Path | None = typer.Option(None, "--file", "-f", help="File with emails to unsuspend."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Unsuspend ALL users in domain."),
) -> None:
    """Bulk unsuspend users (re-enable login). Idempotent."""
    runtime = get_context(ctx)
    emails = _resolve_user_targets(runtime, file=file, domain=domain)
    if not emails:
        return

    from gsm.clients.google_admin import GoogleAdminError

    success = 0
    for email in emails:
        try:
            runtime.admin.unsuspend_user(email)
            success += 1
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Unsuspended {success}/{len(emails)} user(s).[/green]")


LICENSE_MAP = {
    "education": ("101031", "1010310003"),
    "gmail-only": ("101031", "1010310008"),
    "education-plus": ("101031", "1010310009"),
    "education-standard": ("101031", "1010310010"),
}


def _assign_licenses(runtime: Any, results: list[Any], license_key: str) -> None:
    from gsm.clients.google_admin import GoogleAdminError

    if license_key in LICENSE_MAP:
        product_id, sku_id = LICENSE_MAP[license_key]
    else:
        parts = license_key.split("/", 1)
        if len(parts) != 2:
            err_console.print(
                f"[yellow][!][/yellow] License '{license_key}' not recognized. "
                f"Valid: {', '.join(LICENSE_MAP.keys())} atau 'productId/skuId'."
            )
            return
        product_id, sku_id = parts

    success = 0
    for r in results:
        if r.kind != ResultKind.SUCCESS:
            continue
        try:
            runtime.admin.assign_license(r.identifier, sku_id, product_id)
            success += 1
        except GoogleAdminError as e:
            err_console.print(f"[yellow][!][/yellow] License {r.identifier}: {e}")
    console.print(f"[green][+][/green] License assigned to {success} user(s).")


def _resolve_user_targets(runtime: Any, *, file: Path | None, domain: str | None) -> list[str]:
    if file:
        from gsm.cli._shared import read_lines
        return read_lines(file)
    if domain:
        from gsm.clients.google_admin import GoogleAdminError
        try:
            ws_users = runtime.admin.list_users(domain=domain)
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {e}")
            raise typer.Exit(code=2) from e
        return [u["primaryEmail"] for u in ws_users if u.get("primaryEmail")]
    err_console.print("[red][-][/red] Harus kasih --domain atau --file.")
    raise typer.Exit(code=2)


@users_app.command("audit")
def users_audit(
    ctx: typer.Context,
    inactive_days: int = typer.Option(30, "--inactive-days", "-d", help="Threshold hari tidak login."),
    domain: str | None = typer.Option(None, "--domain", help="Filter by domain."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Save inactive emails ke file."),
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

    if inactive:
        table = Table(title=f"Inactive users (>{inactive_days} days, {len(inactive)} found)")
        table.add_column("Email")
        table.add_column("Last Login")
        table.add_column("Days Ago", justify="right")
        for email, last, days in sorted(inactive, key=lambda x: -x[2])[:100]:
            table.add_row(email, last, str(days) if days < 9999 else "never")
        console.print(table)
    else:
        console.print(f"[green][+] All {active} users logged in within {inactive_days} days.[/green]")

    console.print(f"\n[green]Active: {active}[/green]  [yellow]Inactive: {len(inactive)}[/yellow]")

    if output and inactive:
        lines = [email for email, _, _ in inactive]
        output.write_text("\n".join(lines) + "\n")
        console.print(f"[green][+][/green] Inactive emails saved to [cyan]{output}[/cyan]")


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
) -> None:
    """Bulk delete users (PERMANENT - 30 day recovery window in Google)."""
    from rich.prompt import Confirm

    runtime = get_context(ctx)
    emails = _resolve_user_targets(runtime, file=file, domain=domain)
    if not emails:
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
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {email}: {e}")
    console.print(f"[green]Deleted {success}/{len(emails)} user(s).[/green]")


@users_app.command("alias-add")
def users_alias_add(
    ctx: typer.Context,
    email: str = typer.Argument(..., help="User email (target)."),
    alias: str = typer.Argument(..., help="Alias email to add."),
) -> None:
    """Add email alias to a user (e.g. info@domain → user@domain)."""
    from gsm.clients.google_admin import GoogleAdminError

    runtime = get_context(ctx)
    try:
        runtime.admin.add_alias(email, alias)
        console.print(f"[green][+][/green] Alias {alias} → {email}")
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
        console.print(f"  • {a} → {email}")


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
