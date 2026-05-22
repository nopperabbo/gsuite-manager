"""`gsm dns apply` - bulk DNS record management from YAML template."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from gsm.cli._shared import batch_progress, get_context

__all__ = ["dns_apply_command"]

console = Console()


def dns_apply_command(
    ctx: typer.Context,
    template: Path = typer.Argument(..., help="YAML template file with DNS records."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Apply to single domain."),
    file: Path | None = typer.Option(None, "--file", "-f", help="File with domain list."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview tanpa apply."),
) -> None:
    """Apply DNS records from YAML template ke domain(s).

    Template format (YAML):
      records:
        - type: TXT
          name: "@"
          content: "v=spf1 include:_spf.google.com ~all"
        - type: CNAME
          name: "mail"
          content: "ghs.googlehosted.com"
    """
    import yaml

    if not template.exists():
        console.print(f"[red][-][/red] Template not found: {template}")
        raise typer.Exit(code=2)

    try:
        data = yaml.safe_load(template.read_text())
    except Exception as e:
        console.print(f"[red][-][/red] Failed to parse YAML: {e}")
        raise typer.Exit(code=2) from e

    records_spec: list[dict[str, Any]] = data.get("records", [])
    if not records_spec:
        console.print("[yellow][!][/yellow] Template has no records defined.")
        return

    runtime = get_context(ctx)

    targets: list[str] = []
    if domain:
        targets = [domain]
    elif file:
        from gsm.cli._shared import read_lines

        targets = read_lines(file)
    else:
        from gsm.models.domain import DomainStatus

        ledger_domains = runtime.ledger.list_domains(status=DomainStatus.VERIFIED)
        targets = [r.name for r in ledger_domains]

    if not targets:
        console.print("[yellow][!][/yellow] No target domains.")
        return

    console.print(
        f"[cyan]Applying {len(records_spec)} record(s) to {len(targets)} domain(s)"
        f"{' (DRY RUN)' if dry_run else ''}[/cyan]\n"
    )

    if dry_run:
        for d in targets[:5]:
            for rec in records_spec:
                name = rec.get("name", "@")
                display_name = d if name == "@" else f"{name}.{d}"
                console.print(
                    f"  [dim]would create[/dim] {rec['type']} {display_name} = {rec['content']}"
                )
        if len(targets) > 5:
            console.print(f"  [dim]... and {len(targets) - 5} more domains[/dim]")
        return

    from gsm.clients.cloudflare import CloudflareError

    success = 0
    failed = 0

    with batch_progress(f"DNS apply ({len(targets)} domains)", len(targets)) as on_progress:
        for idx, d in enumerate(targets, 1):
            zone = runtime.cf.get_zone_by_name(d)
            if zone is None:
                console.print(f"[red][-][/red] {d}: no CF zone found, skip")
                failed += 1
                from gsm.models.results import ItemResult

                on_progress(idx, len(targets), d, ItemResult.failed(d, "no zone"))
                continue
            domain_ok = True
            for rec in records_spec:
                try:
                    runtime.cf.upsert_dns_record(
                        zone.zone_id,
                        record_type=rec["type"],
                        name=d if rec.get("name", "@") == "@" else f"{rec['name']}.{d}",
                        content=rec["content"],
                        priority=rec.get("priority"),
                        ttl=rec.get("ttl", 1),
                        proxied=rec.get("proxied", False),
                    )
                except CloudflareError as e:
                    console.print(f"[red][-][/red] {d} {rec['type']}: {e}")
                    domain_ok = False
            if domain_ok:
                success += 1
            else:
                failed += 1
            from gsm.models.results import ItemResult

            on_progress(
                idx,
                len(targets),
                d,
                ItemResult.success(d, "ok") if domain_ok else ItemResult.failed(d, "partial"),
            )

    console.print(f"\n[green]success={success}[/green]  [red]failed={failed}[/red]")
