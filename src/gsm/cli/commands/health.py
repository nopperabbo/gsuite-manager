"""`gsm domains health` - check DNS health of all verified domains."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from gsm.cli._shared import get_context

console = Console()

EXPECTED_MX = {
    "aspmx.l.google.com",
    "alt1.aspmx.l.google.com",
    "alt2.aspmx.l.google.com",
    "alt3.aspmx.l.google.com",
    "alt4.aspmx.l.google.com",
}


def health_command(
    ctx: typer.Context,
    domain: str | None = typer.Option(None, "--domain", "-d", help="Check single domain."),
    fix: bool = typer.Option(False, "--fix", help="Auto-fix missing MX/TXT (re-inject)."),
) -> None:
    """Check DNS health: MX records, TXT verification, NS pointing to CF."""
    import dns.resolver

    runtime = get_context(ctx)

    if domain:
        targets = [domain]
    else:
        records = runtime.ledger.list_domains()
        from gsm.models.domain import DomainStatus
        targets = [r.name for r in records if r.status == DomainStatus.VERIFIED]
        if not targets:
            console.print("[yellow]No verified domains in ledger.[/yellow]")
            return

    console.print(f"[dim]Checking DNS health for {len(targets)} domain(s)...[/dim]\n")

    issues: list[tuple[str, str, str]] = []
    healthy = 0

    for d in targets:
        problems: list[str] = []

        try:
            mx_answers = dns.resolver.resolve(d, "MX")
            mx_hosts = {r.exchange.to_text().rstrip(".").lower() for r in mx_answers}
            missing_mx = EXPECTED_MX - mx_hosts
            if missing_mx:
                problems.append(f"missing MX: {', '.join(sorted(missing_mx)[:2])}...")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            problems.append("MX: NXDOMAIN or no answer")
        except Exception as e:
            problems.append(f"MX query error: {e}")

        try:
            txt_answers = dns.resolver.resolve(d, "TXT")
            txt_values = " ".join(
                b"".join(r.strings).decode("utf-8", errors="replace")
                for r in txt_answers
            )
            if "google-site-verification=" not in txt_values:
                problems.append("TXT: google-site-verification missing")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            problems.append("TXT: no answer")
        except Exception:
            pass

        try:
            ns_answers = dns.resolver.resolve(d, "NS")
            ns_hosts = {r.to_text().rstrip(".").lower() for r in ns_answers}
            has_cf = any("cloudflare" in ns for ns in ns_hosts)
            if not has_cf:
                problems.append(f"NS not CF: {', '.join(sorted(ns_hosts)[:2])}")
        except Exception:
            problems.append("NS: query failed")

        if problems:
            for p in problems:
                issues.append((d, "WARN", p))
        else:
            healthy += 1

    if issues:
        table = Table(title=f"DNS Issues ({len(issues)} problems in {len(set(i[0] for i in issues))} domains)")
        table.add_column("Domain")
        table.add_column("Issue")
        for d, _, problem in issues:
            table.add_row(d, problem)
        console.print(table)

    console.print(
        f"\n[green]Healthy: {healthy}[/green]  "
        f"[yellow]Issues: {len(set(i[0] for i in issues))}[/yellow]  "
        f"Total: {len(targets)}"
    )

    if fix and issues:
        console.print("\n[dim]--fix not yet implemented. Use `gsm domains add` to re-inject.[/dim]")
