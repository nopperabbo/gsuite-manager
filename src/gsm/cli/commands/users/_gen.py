"""Generation commands: gen."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import SecretStr

from gsm.cli._shared import batch_progress, console, err_console, get_context, render_results
from gsm.cli.commands.users._app import users_app
from gsm.cli.commands.users._helpers import _assign_licenses
from gsm.clients.username_generator import (
    DEFAULT_COLLISION_FALLBACK,
    DEFAULT_PASSWORD_LENGTH,
    DEFAULT_PATTERN,
    GeneratedAccount,
    GeneratorError,
    generate_accounts,
)
from gsm.models.results import ResultKind
from gsm.models.user import AccountSpec
from gsm.workflows.user_bulk_create import create_users

__all__ = ["users_gen"]


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
