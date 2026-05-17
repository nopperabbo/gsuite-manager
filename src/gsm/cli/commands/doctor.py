"""`gsm doctor` - 5 health checks for setup verification.

Checks:
  1. Settings load (.env + GSM_* parsing)
  2. OAuth client file detected
  3. Cloudflare connectivity (token + account_id are valid)
  4. DNS resolvers reachable
  5. Ledger path is writable
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import dns.exception
import dns.resolver
import requests
import typer
from rich.table import Table

from gsm.cli._shared import console
from gsm.clients.cloudflare import CF_BASE_URL
from gsm.core.auth import detect_oauth_client_file
from gsm.core.config import load_settings


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def doctor_command() -> None:
    """Run all health checks and print a summary table."""
    results: list[CheckResult] = []

    settings = None
    try:
        settings = load_settings()
        results.append(
            CheckResult(
                "settings",
                True,
                f"loaded from .env (log_level={settings.log_level}, "
                f"log_format={settings.log_format})",
            )
        )
    except (ValueError, OSError) as e:
        results.append(CheckResult("settings", False, f"failed to load: {e}"))

    if settings is None:
        _print_results(results)
        raise typer.Exit(code=1)

    results.append(_check_oauth_client(settings.google_oauth_client_path))
    results.append(_check_cloudflare(settings.cf_api_token.get_secret_value()))
    results.append(_check_dns_resolvers(settings.dns_check_resolvers))
    results.append(_check_ledger_writable(settings.ledger_path))

    _print_results(results)
    if not all(r.ok for r in results):
        raise typer.Exit(code=1)


def _check_oauth_client(configured_path: Path) -> CheckResult:
    if configured_path.exists():
        return CheckResult(
            "oauth_client", True, f"found at {configured_path}"
        )
    detected = detect_oauth_client_file(configured_path.parent or Path.cwd())
    if detected is None:
        return CheckResult(
            "oauth_client",
            False,
            f"not found at {configured_path} and no client_secret_*.json detected",
        )
    return CheckResult(
        "oauth_client", True, f"detected at {detected} (configured path missing)"
    )


def _check_cloudflare(token: str) -> CheckResult:
    try:
        resp = requests.get(
            f"{CF_BASE_URL}/user/tokens/verify",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        data = resp.json()
        if data.get("success"):
            status = data.get("result", {}).get("status", "unknown")
            return CheckResult(
                "cloudflare", True, f"token valid (status={status})"
            )
        msg = "; ".join(
            e.get("message", "?") for e in data.get("errors", [])
        )
        return CheckResult("cloudflare", False, f"token invalid: {msg}")
    except requests.RequestException as e:
        return CheckResult("cloudflare", False, f"request failed: {e}")


def _check_dns_resolvers(resolvers: list[str]) -> CheckResult:
    healthy: list[str] = []
    for ip in resolvers:
        try:
            r = dns.resolver.Resolver(configure=False)
            r.nameservers = [ip]
            r.timeout = 3.0
            r.lifetime = 3.0
            r.resolve("google.com", "A")
            healthy.append(ip)
        except (dns.exception.DNSException, OSError):
            continue
    if not healthy:
        return CheckResult(
            "dns_resolvers", False, f"none of {resolvers} reachable"
        )
    return CheckResult(
        "dns_resolvers",
        True,
        f"{len(healthy)}/{len(resolvers)} reachable: {', '.join(healthy)}",
    )


def _check_ledger_writable(path: Path) -> CheckResult:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.with_suffix(path.suffix + ".write_test")
        probe.write_text("{}", encoding="utf-8")
        probe.unlink()
        return CheckResult("ledger", True, f"writable at {path}")
    except OSError as e:
        return CheckResult("ledger", False, f"not writable: {e}")


def _print_results(results: list[CheckResult]) -> None:
    table = Table(title="gsm doctor")
    table.add_column("#", no_wrap=True)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for idx, r in enumerate(results, start=1):
        status = "[green]PASS[/green]" if r.ok else "[red]FAIL[/red]"
        table.add_row(str(idx), r.name, status, r.detail)
    console.print(table)
    failed = sum(1 for r in results if not r.ok)
    if failed:
        console.print(f"[red]{failed} check(s) failed.[/red]")
    else:
        console.print("[green]All checks passed.[/green]")
