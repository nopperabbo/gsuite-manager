"""`gsm go` - all-in-one shortcut. Detect files, do everything, print summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel

from gsm.cli._shared import batch_progress, get_context, render_results
from gsm.models.results import ResultKind

__all__ = ["go_command"]

console = Console()


def go_command(
    ctx: typer.Context,
    domains: Path | None = typer.Option(
        None, "--domains", "-d", help="File domain list. Default: auto-detect domains.txt di CWD."
    ),
    users: Path | None = typer.Option(
        None, "--users", "-u", help="File akun.txt. Default: auto-detect akun.txt di CWD."
    ),
    skip_domains: bool = typer.Option(False, "--skip-domains", help="Skip domain onboarding."),
    skip_users: bool = typer.Option(False, "--skip-users", help="Skip user creation."),
) -> None:
    """All-in-one: onboard domains + create users. Auto-detect files di CWD."""
    domains_file = domains or _find_file("domains.txt", "domains.csv")
    users_file = users or _find_file("akun.txt", "users.txt", "accounts.txt")

    if not domains_file and not users_file:
        console.print(
            Panel.fit(
                "[yellow]Gak nemu file domains atau akun di folder ini.[/yellow]\n\n"
                "Taruh salah satu (atau dua-duanya) di folder sekarang:\n"
                "  • [cyan]domains.txt[/cyan] - 1 domain per baris\n"
                "  • [cyan]akun.txt[/cyan] - format: email | password | code\n\n"
                "Atau specify manual:\n"
                "  [dim]gsm go --domains path/to/domains.txt --users path/to/akun.txt[/dim]",
                title="gsm go",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=0)

    runtime = get_context(ctx)

    domain_results = []
    user_results = []

    if domains_file and not skip_domains:
        from gsm.cli._shared import read_lines
        from gsm.workflows.domain_onboarding import onboard_domains

        targets = read_lines(domains_file)
        if targets:
            console.print(
                f"\n[bold cyan]Step 1:[/bold cyan] Onboarding "
                f"[green]{len(targets)}[/green] domain(s) dari [cyan]{domains_file.name}[/cyan]"
            )
            with batch_progress(f"Domains ({len(targets)})", len(targets)) as on_progress:
                domain_results = onboard_domains(
                    targets,
                    settings=runtime.settings,
                    ledger=runtime.ledger,
                    cf=runtime.cf,
                    admin=runtime.admin,
                    verify=runtime.verify,
                    on_progress=on_progress,
                )
            render_results(domain_results, title="Domain Results")

    if users_file and not skip_users:
        from gsm.workflows.user_bulk_create import create_users, parse_akun_file

        accounts = parse_akun_file(users_file)
        if accounts:
            console.print(
                f"\n[bold cyan]Step 2:[/bold cyan] Creating "
                f"[green]{len(accounts)}[/green] user(s) dari [cyan]{users_file.name}[/cyan]"
            )
            with batch_progress(f"Users ({len(accounts)})", len(accounts)) as on_progress:
                user_results = create_users(
                    accounts,
                    settings=runtime.settings,
                    ledger=runtime.ledger,
                    admin=runtime.admin,
                    on_progress=on_progress,
                )
            render_results(user_results, title="User Results")

    _print_summary(domain_results, user_results, domains_file, users_file)


def _find_file(*names: str) -> Path | None:
    cwd = Path.cwd()
    for name in names:
        path = cwd / name
        if path.exists():
            return path
    return None


def _print_summary(
    domain_results: list[Any],
    user_results: list[Any],
    domains_file: Path | None,
    users_file: Path | None,
) -> None:
    parts: list[str] = []

    if domain_results:
        ds = sum(1 for r in domain_results if r.kind == ResultKind.SUCCESS)
        df = sum(1 for r in domain_results if r.kind == ResultKind.FAILED)
        dp = sum(1 for r in domain_results if r.kind == ResultKind.PARTIAL)
        parts.append(
            f"Domains: [green]{ds} verified[/green]"
            + (f"  [yellow]{dp} pending[/yellow]" if dp else "")
            + (f"  [red]{df} failed[/red]" if df else "")
        )

    if user_results:
        us = sum(1 for r in user_results if r.kind == ResultKind.SUCCESS)
        uf = sum(1 for r in user_results if r.kind == ResultKind.FAILED)
        parts.append(
            f"Users: [green]{us} created[/green]" + (f"  [red]{uf} failed[/red]" if uf else "")
        )

    if not parts:
        parts.append("[dim]Nothing to do.[/dim]")

    console.print(
        Panel.fit(
            "\n".join(parts),
            title="[bold]Summary[/bold]",
            border_style="green"
            if all(r.kind != ResultKind.FAILED for r in [*domain_results, *user_results])
            else "yellow",
        )
    )
