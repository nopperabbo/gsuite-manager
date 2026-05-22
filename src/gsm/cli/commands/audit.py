"""`gsm audit` - reconcile state between Cloudflare and Workspace.

Identifies domains in 4 categories:
  1. CF + Workspace (verified) - all good
  2. CF only - needs onboarding to Workspace
  3. Workspace only - missing CF zone (rare, manual fix)
  4. Neither - in ledger but lost (cleanup needed)

Output suggests next action per gap (e.g. `gsm domains add ...`).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from gsm.cli._shared import err_console, get_context
from gsm.clients.cloudflare import CloudflareError
from gsm.clients.google_admin import GoogleAdminError
from gsm.core.errors import humanize

__all__ = ["audit_command"]

console = Console()


def audit_command(
    ctx: typer.Context,
    show_synced: bool = typer.Option(
        False,
        "--show-synced",
        help="Tampilkan juga domain yang udah sinkron (default: hanya gap).",
    ),
    output_file: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Tulis daftar gap ke file (untuk dipakai gsm domains add --file).",
    ),
) -> None:
    """Audit: cek domain mana yang ada di CF tapi belum di Workspace (atau sebaliknya)."""
    runtime = get_context(ctx)

    console.print("[dim]Mengambil daftar zone dari Cloudflare...[/dim]")
    try:
        cf_zones = runtime.cf.list_zones()
    except CloudflareError as e:
        err_console.print(f"[red][-][/red] {humanize(e).render()}")
        raise typer.Exit(code=2) from e
    cf_domains = {z.name for z in cf_zones}
    console.print(f"[green][+][/green] {len(cf_domains)} zone di Cloudflare")

    console.print("[dim]Mengambil daftar domain dari Google Workspace...[/dim]")
    try:
        ws_domain_records = runtime.admin.list_domains()
    except GoogleAdminError as e:
        err_console.print(f"[red][-][/red] {humanize(e).render()}")
        raise typer.Exit(code=2) from e

    ws_domains: set[str] = set()
    ws_verified: set[str] = set()
    for raw in ws_domain_records:
        name = raw.get("domainName", "").lower()
        if not name:
            continue
        ws_domains.add(name)
        if raw.get("verified"):
            ws_verified.add(name)
    console.print(
        f"[green][+][/green] {len(ws_domains)} domain di Workspace ({len(ws_verified)} verified)"
    )

    cf_only = sorted(cf_domains - ws_domains)
    ws_only = sorted(ws_domains - cf_domains)
    both = sorted(cf_domains & ws_domains)
    both_verified = [d for d in both if d in ws_verified]
    both_unverified = [d for d in both if d not in ws_verified]

    console.print()
    summary = Table(title="Audit Summary", show_header=False)
    summary.add_column("Kategori")
    summary.add_column("Count", justify="right")
    summary.add_column("Action")
    summary.add_row(
        "[green]CF + Workspace verified[/green]",
        str(len(both_verified)),
        "[dim]No action[/dim]",
    )
    summary.add_row(
        "[yellow]CF + Workspace (not verified)[/yellow]",
        str(len(both_unverified)),
        "Run: gsm domains verify --only-pending",
    )
    summary.add_row(
        "[red]CF only (gap)[/red]",
        str(len(cf_only)),
        "Run: gsm domains add ...",
    )
    summary.add_row(
        "[magenta]Workspace only (rare)[/magenta]",
        str(len(ws_only)),
        "Manual: add zone ke CF, lalu re-onboard",
    )
    console.print(summary)

    if cf_only:
        console.print()
        console.print(f"[bold red]{len(cf_only)} domain di CF tapi belum di Workspace:[/bold red]")
        gap_table = Table(show_header=True, header_style="bold cyan")
        gap_table.add_column("#", justify="right", width=4)
        gap_table.add_column("Domain")
        for i, d in enumerate(cf_only, 1):
            gap_table.add_row(str(i), d)
        console.print(gap_table)

        if output_file:
            from pathlib import Path

            Path(output_file).write_text("\n".join(cf_only) + "\n")
            console.print(f"\n[green][+][/green] Daftar di-write ke [cyan]{output_file}[/cyan]")
            console.print(f"[dim]Run: gsm domains add --file {output_file}[/dim]")
        else:
            console.print(
                "\n[dim]Tip: tambahin --output <file> untuk simpan list,[/dim]\n"
                "[dim]     atau langsung: "
                f"gsm domains add {' '.join(cf_only[:3])}"
                f"{' ...' if len(cf_only) > 3 else ''}[/dim]"
            )

    if ws_only:
        console.print()
        console.print(
            f"[bold magenta]{len(ws_only)} domain di Workspace tapi gak ada zone CF:[/bold magenta]"
        )
        for d in ws_only:
            console.print(f"  • {d}")

    if show_synced and both_verified:
        console.print()
        console.print(
            f"[bold green]{len(both_verified)} domain udah sinkron (verified):[/bold green]"
        )
        for d in both_verified:
            console.print(f"  ✓ {d}")

    if not cf_only and not ws_only and not both_unverified:
        console.print()
        console.print("[bold green]Semua domain udah sinkron dan terverifikasi![/bold green]")
