"""`gsm domains check-expiry` - check domain expiry via RDAP/WHOIS."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from gsm.cli._shared import get_context

console = Console()


def check_expiry_command(
    ctx: typer.Context,
    days: int = typer.Option(30, "--days", "-d", help="Alert threshold (days until expiry)."),
    domain: str | None = typer.Option(None, "--domain", help="Check single domain."),
) -> None:
    """Check domain expiry dates. Alert domains expiring within --days."""
    import json
    import urllib.error
    import urllib.request

    runtime = get_context(ctx)

    if domain:
        targets = [domain]
    else:
        records = runtime.ledger.list_domains()
        from gsm.models.domain import DomainStatus
        targets = [r.name for r in records if r.status == DomainStatus.VERIFIED]
        if not targets:
            console.print("[yellow]No verified domains in ledger to check.[/yellow]")
            return

    console.print(f"[dim]Checking expiry for {len(targets)} domain(s) via RDAP...[/dim]\n")

    expiring: list[tuple[str, datetime, int]] = []
    errors: list[tuple[str, str]] = []
    ok_count = 0

    now = datetime.now(UTC)
    threshold = now + timedelta(days=days)

    for d in targets:
        rdap_url = f"https://rdap.org/domain/{d}"
        try:
            req = urllib.request.Request(rdap_url, headers={"Accept": "application/rdap+json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            events = data.get("events", [])
            exp_date = None
            for ev in events:
                if ev.get("eventAction") == "expiration":
                    date_str = ev.get("eventDate", "")
                    exp_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    break
            if exp_date is None:
                errors.append((d, "no expiry date in RDAP"))
                continue
            days_left = (exp_date - now).days
            if exp_date <= threshold:
                expiring.append((d, exp_date, days_left))
            else:
                ok_count += 1
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
            errors.append((d, str(e)[:80]))
        except Exception as e:
            errors.append((d, str(e)[:80]))

    if expiring:
        table = Table(title=f"⚠️  Expiring within {days} days ({len(expiring)} domains)")
        table.add_column("Domain")
        table.add_column("Expires", justify="right")
        table.add_column("Days Left", justify="right")
        for d, exp, dl in sorted(expiring, key=lambda x: x[2]):
            color = "red" if dl <= 7 else "yellow"
            table.add_row(d, exp.strftime("%Y-%m-%d"), f"[{color}]{dl}[/{color}]")
        console.print(table)
    else:
        console.print(f"[green][+] No domains expiring within {days} days.[/green]")

    if errors:
        console.print(f"\n[dim]{len(errors)} domain(s) couldn't be checked (RDAP unavailable).[/dim]")

    console.print(
        f"\n[green]OK: {ok_count}[/green]  "
        f"[yellow]Expiring: {len(expiring)}[/yellow]  "
        f"[dim]Errors: {len(errors)}[/dim]"
    )
