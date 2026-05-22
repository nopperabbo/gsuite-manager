"""`gsm domains` subcommands: add, verify, list, check-mx, import."""

from __future__ import annotations

from pathlib import Path

import typer

from gsm.cli._shared import (
    batch_progress,
    console,
    err_console,
    get_context,
    read_lines,
    render_interrupted_summary,
    render_results,
)
from gsm.clients.cloudflare import CloudflareError
from gsm.clients.mx_check import MxStatus, check_mx
from gsm.core.errors import humanize
from gsm.models.domain import DomainStatus
from gsm.models.results import ResultKind
from gsm.workflows.domain_import import (
    ImportableZone,
    ImportClassification,
    discover_importable_zones,
    filter_actionable,
    label_for,
    zone_names_only,
)
from gsm.workflows.domain_onboarding import DomainOnboarder, onboard_domains

__all__ = [
    "domains_add",
    "domains_app",
    "domains_check_mx",
    "domains_import",
    "domains_list",
    "domains_verify",
]

domains_app = typer.Typer(
    name="domains",
    help="Manage Workspace domains: onboard, verify, inspect.",
    no_args_is_help=True,
)


@domains_app.command("add")
def domains_add(
    ctx: typer.Context,
    domain: list[str] = typer.Argument(
        None,
        help="One or more domain names (alternative to --file).",
    ),
    file: Path | None = typer.Option(
        None, "--file", "-f", help="Read domains from file (one per line)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview tanpa apply."),
) -> None:
    """Onboard one or more domains end-to-end (add -> CF zone -> DNS -> verify)."""
    targets = _collect_domains(domain, file)
    if dry_run:
        console.print(
            f"[dim]--dry-run: would onboard {len(targets)} domain(s): {', '.join(targets[:5])}{'...' if len(targets) > 5 else ''}[/dim]"
        )
        return
    runtime = get_context(ctx)
    with batch_progress(f"Onboarding {len(targets)} domain(s)", len(targets)) as on_progress:
        results = onboard_domains(
            targets,
            settings=runtime.settings,
            ledger=runtime.ledger,
            cf=runtime.cf,
            admin=runtime.admin,
            verify=runtime.verify,
            on_progress=on_progress,
        )
    if len(results) < len(targets):
        render_interrupted_summary(results, len(targets))
        raise typer.Exit(code=130)
    render_results(results, title=f"Onboarding {len(targets)} domain(s)")
    if any(r.kind is ResultKind.FAILED for r in results):
        raise typer.Exit(code=1)


@domains_app.command("verify")
def domains_verify(
    ctx: typer.Context,
    domain: list[str] = typer.Argument(
        None,
        help="Domain(s) to retry verification on (alternative to --file).",
    ),
    file: Path | None = typer.Option(None, "--file", "-f", help="Read domains from file."),
    only_pending: bool = typer.Option(
        False,
        "--only-pending",
        help="Verify all domains in DNS_PENDING / DNS_INJECTED state from ledger.",
    ),
) -> None:
    """Re-run verification for domains stuck in DNS_PENDING (DNS not propagated yet)."""
    runtime = get_context(ctx)
    if only_pending:
        targets = [
            r.name
            for r in runtime.ledger.list_domains()
            if r.status in (DomainStatus.DNS_PENDING, DomainStatus.DNS_INJECTED)
        ]
        if not targets:
            typer.echo("No domains in DNS_PENDING/DNS_INJECTED state.")
            return
    else:
        targets = _collect_domains(domain, file)

    onboarder = DomainOnboarder(
        settings=runtime.settings,
        ledger=runtime.ledger,
        cf=runtime.cf,
        admin=runtime.admin,
        verify=runtime.verify,
    )
    results = [onboarder.run(d) for d in targets]
    render_results(results, title=f"Verifying {len(targets)} domain(s)")
    if any(r.kind is ResultKind.FAILED for r in results):
        raise typer.Exit(code=1)


@domains_app.command("list")
def domains_list(
    ctx: typer.Context,
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by status: PENDING, GSUITE_ADDED, TOKEN_FETCHED, "
        "CF_ZONE_READY, DNS_INJECTED, DNS_PENDING, VERIFIED, FAILED.",
    ),
) -> None:
    """List domains tracked in the ledger, optionally filtered by status."""
    from rich.table import Table

    from gsm.cli._shared import console

    runtime = get_context(ctx)
    status_filter = None
    if status is not None:
        try:
            status_filter = DomainStatus(status.lower())
        except ValueError as e:
            raise typer.BadParameter(
                f"unknown status: {status}. Valid: {', '.join(s.value for s in DomainStatus)}"
            ) from e

    records = runtime.ledger.list_domains(status=status_filter)
    if not records:
        typer.echo("(no domains in ledger)")
        return

    table = Table(title=f"Domains ({len(records)})")
    table.add_column("Domain")
    table.add_column("Status")
    table.add_column("Zone ID")
    table.add_column("Last Updated")
    table.add_column("Last Error")

    for r in records:
        table.add_row(
            r.name,
            r.status.value,
            r.cf_zone_id or "-",
            r.last_updated.strftime("%Y-%m-%d %H:%M"),
            (r.last_error or "")[:60],
        )
    console.print(table)


def _collect_domains(positional: list[str] | None, file: Path | None) -> list[str]:
    if file is not None:
        return read_lines(file)
    if positional:
        return positional
    raise typer.BadParameter("provide either positional domain(s) or --file FILE")


@domains_app.command("check-mx")
def domains_check_mx(
    ctx: typer.Context,
    domain: list[str] = typer.Argument(
        None,
        help="One or more domain names to check (alternative to --file or --all).",
    ),
    file: Path | None = typer.Option(
        None, "--file", "-f", help="Read domains from file (one per line)."
    ),
    check_all: bool = typer.Option(
        False,
        "--all",
        help="Check semua domain di ledger yang status-nya VERIFIED.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output dalam JSON (untuk scripting). Suppresses log output to stdout.",
    ),
) -> None:
    """Cek MX records: domain udah pointing ke Google Workspace mail server (Gmail aktif)?"""
    runtime = get_context(ctx)

    if check_all:
        targets = [r.name for r in runtime.ledger.list_domains(status=DomainStatus.VERIFIED)]
        if not targets:
            typer.echo("Tidak ada domain VERIFIED di ledger.")
            return
    else:
        targets = _collect_domains(domain, file)

    if json_output:
        results = _check_mx_silent(targets, runtime.settings)
        _print_json(results)
    else:
        results = [check_mx(d, runtime.settings) for d in targets]
        _print_mx_table(results)

    has_unhealthy = any(not r.is_healthy for r in results)
    if has_unhealthy:
        raise typer.Exit(code=1)


def _check_mx_silent(domains: list[str], settings):  # type: ignore[no-untyped-def]
    """Run check_mx for each domain while silencing structlog output to stdout.

    structlog is configured globally to write to stdout (RichHandler) which
    would corrupt JSON output. We swap stdout to /dev/null only during the
    network calls, then restore it before printing JSON.
    """
    import io
    import sys

    real_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        return [check_mx(d, settings) for d in domains]
    finally:
        sys.stdout = real_stdout


@domains_app.command("import")
def domains_import(
    ctx: typer.Context,
    source: str = typer.Option(
        "cloudflare",
        "--from",
        help="Source untuk import zone (saat ini: 'cloudflare').",
    ),
    filter_glob: str | None = typer.Option(
        None,
        "--filter",
        help="Glob pattern filter (mis. '*.tech', 'sub.*'). Case-insensitive.",
    ),
    select_all: bool = typer.Option(
        False,
        "--all",
        help="Skip interactive picker, langsung onboard semua zone yang actionable.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Tampilkan zone yang ditemukan tanpa onboard apa-apa.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Tulis nama domain yang dipilih ke file (untuk pipe ke `domains add --file`).",
    ),
) -> None:
    """Import zone dari Cloudflare ke ledger + onboard ke Workspace (interactive picker by default)."""
    runtime = get_context(ctx)

    if source.lower() != "cloudflare":
        err_console.print(
            f"[red][-][/red] Source tidak didukung: {source!r}. Saat ini cuma 'cloudflare'."
        )
        raise typer.Exit(code=2)

    console.print("[dim]Mengambil daftar zone dari Cloudflare...[/dim]")
    try:
        zones = discover_importable_zones(runtime.cf, runtime.ledger, filter_glob=filter_glob)
    except CloudflareError as e:
        err_console.print(f"[red][-][/red] {humanize(e).render()}")
        raise typer.Exit(code=2) from e

    if not zones:
        msg = "Tidak ada zone di Cloudflare account ini."
        if filter_glob:
            msg += f" (filter: {filter_glob})"
        console.print(msg)
        return

    _print_discovery_summary(zones)

    actionable = filter_actionable(zones)
    if not actionable:
        console.print(
            "\n[green]Semua zone sudah VERIFIED di Workspace - tidak ada yang perlu di-import.[/green]"
        )
        return

    if dry_run:
        console.print(
            f"\n[dim]--dry-run: ada {len(actionable)} zone yang bisa di-import. "
            "Run tanpa --dry-run untuk pilih + onboard.[/dim]"
        )
        return

    if select_all:
        selected_names = zone_names_only(actionable)
        console.print(
            f"\n[bold]--all: akan onboard semua {len(selected_names)} zone yang actionable.[/bold]"
        )
    else:
        selected_names = _interactive_pick(actionable)
        if not selected_names:
            console.print("\n[yellow]Tidak ada zone yang dipilih. Batal.[/yellow]")
            return

    if output is not None:
        _write_domain_list(output, selected_names)
        console.print(
            f"[green][+][/green] {len(selected_names)} domain ditulis ke [cyan]{output}[/cyan]"
        )
        console.print(f"[dim]Run: gsm domains add --file {output}[/dim]")
        return

    console.print(f"\n[bold]Onboarding {len(selected_names)} domain...[/bold]")
    with batch_progress(
        f"Onboarding {len(selected_names)} domain", len(selected_names)
    ) as on_progress:
        results = onboard_domains(
            selected_names,
            settings=runtime.settings,
            ledger=runtime.ledger,
            cf=runtime.cf,
            admin=runtime.admin,
            verify=runtime.verify,
            on_progress=on_progress,
        )
    render_results(results, title=f"Imported {len(selected_names)} domain(s)")
    if any(r.kind is ResultKind.FAILED for r in results):
        raise typer.Exit(code=1)


def _print_discovery_summary(zones: list[ImportableZone]) -> None:
    from rich.table import Table

    counts = {
        ImportClassification.NEW: 0,
        ImportClassification.ALREADY_IMPORTED: 0,
        ImportClassification.ALREADY_VERIFIED: 0,
    }
    for z in zones:
        counts[z.classification] += 1

    summary = Table(title=f"Discovered {len(zones)} zone di Cloudflare", show_header=False)
    summary.add_column("Kategori")
    summary.add_column("Count", justify="right")
    summary.add_row(
        "[green]NEW (belum pernah di-import)[/green]", str(counts[ImportClassification.NEW])
    )
    summary.add_row(
        "[yellow]Sudah di-import (in progress)[/yellow]",
        str(counts[ImportClassification.ALREADY_IMPORTED]),
    )
    summary.add_row(
        "[dim]Sudah VERIFIED (skip otomatis)[/dim]",
        str(counts[ImportClassification.ALREADY_VERIFIED]),
    )
    console.print(summary)


def _interactive_pick(actionable: list[ImportableZone]) -> list[str]:
    """Show questionary checkbox picker. Returns list of selected domain names."""
    import questionary

    new_zones = [z for z in actionable if z.classification is ImportClassification.NEW]
    in_progress_zones = [
        z for z in actionable if z.classification is ImportClassification.ALREADY_IMPORTED
    ]

    choices = []
    for z in new_zones:
        choices.append(
            questionary.Choice(
                title=f"{z.name}  [NEW]",
                value=z.name,
                checked=True,
            )
        )
    for z in in_progress_zones:
        choices.append(
            questionary.Choice(
                title=f"{z.name}  [{label_for(z)}]",
                value=z.name,
                checked=False,
            )
        )

    answer = questionary.checkbox(
        "Pilih domain yang mau di-onboard (space=toggle, enter=confirm):",
        choices=choices,
    ).ask()

    if answer is None:
        return []
    return list(answer)


def _write_domain_list(path: Path, names: list[str]) -> None:
    """Write one domain per line, mode 0644 (no secrets here)."""
    import contextlib

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(names) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        path.chmod(0o644)


def _print_mx_table(results: list) -> None:  # type: ignore[type-arg]
    from rich.table import Table

    from gsm.clients.mx_check import MxCheckResult

    typed: list[MxCheckResult] = list(results)

    table = Table(title=f"MX Health Check ({len(typed)} domain)")
    table.add_column("Domain")
    table.add_column("Status", no_wrap=True)
    table.add_column("Provider")
    table.add_column("Records", justify="right")
    table.add_column("Notes")

    style_map = {
        MxStatus.HEALTHY: "green",
        MxStatus.PARTIAL: "yellow",
        MxStatus.NOT_GOOGLE: "red",
        MxStatus.NO_MX: "red",
        MxStatus.ERROR: "red",
    }

    for r in typed:
        style = style_map.get(r.status, "white")
        notes = "; ".join(r.diagnostics) if r.diagnostics else (r.error or "")
        table.add_row(
            r.domain,
            f"[{style}]{r.status.value}[/{style}]",
            r.detected_provider or "-",
            str(len(r.actual_records)),
            notes[:60],
        )
    console.print(table)

    healthy = sum(1 for r in typed if r.is_healthy)
    console.print(f"[green]healthy[/green]={healthy}  [red]unhealthy[/red]={len(typed) - healthy}")

    for r in typed:
        if r.is_healthy:
            continue
        err_console.print()
        err_console.print(
            f"[bold]{r.domain}[/bold] - [{style_map[r.status]}]{r.status.value}[/{style_map[r.status]}]"
        )
        if r.actual_records:
            err_console.print("  [dim]MX terdeteksi:[/dim]")
            for rec in sorted(r.actual_records, key=lambda x: x.priority):
                err_console.print(f"    {rec.priority:>3}  {rec.host}")
        if r.missing_records:
            err_console.print("  [dim]MX Google yang missing:[/dim]")
            for host, prio in r.missing_records:
                err_console.print(f"    {prio:>3}  {host}")
        for note in r.diagnostics:
            err_console.print(f"  [yellow]i[/yellow] {note}")
        if r.error:
            err_console.print(f"  [red]![/red] {r.error}")


def _print_json(results: list) -> None:  # type: ignore[type-arg]
    import json

    from gsm.clients.mx_check import MxCheckResult

    typed: list[MxCheckResult] = list(results)
    payload = [
        {
            "domain": r.domain,
            "status": r.status.value,
            "is_healthy": r.is_healthy,
            "detected_provider": r.detected_provider,
            "actual_records": [
                {"host": rec.host, "priority": rec.priority} for rec in r.actual_records
            ],
            "missing_records": [
                {"host": host, "priority": prio} for host, prio in r.missing_records
            ],
            "diagnostics": list(r.diagnostics),
            "error": r.error,
        }
        for r in typed
    ]
    typer.echo(json.dumps(payload, indent=2))
