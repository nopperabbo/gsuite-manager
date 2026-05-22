"""DNS propagation pre-check.

Polls multiple public resolvers (default: 8.8.8.8 + 1.1.1.1) for the expected
TXT record before triggering Google site verification.

Fixes the legacy race condition where verification was called immediately after
DNS injection: 271 failures in production logs were caused by Google querying
DNS before the TXT record had propagated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import dns.exception
import dns.resolver

from gsm.core.config import Settings

__all__ = ["DnsCheckResult", "wait_for_txt"]


@dataclass(frozen=True)
class DnsCheckResult:
    """Outcome of a DNS propagation poll."""

    propagated: bool
    attempts: int
    elapsed_sec: float
    last_error: str | None
    resolvers_seen: list[str]


def wait_for_txt(
    domain: str,
    expected_token: str,
    settings: Settings,
    *,
    sleep: object | None = None,
) -> DnsCheckResult:
    """Poll resolvers until expected_token is found in domain's TXT record set.

    Backoff schedule defined by settings.dns_check_backoff_sec (per-attempt sleep).
    Stops after settings.dns_check_max_attempts attempts.

    `sleep` parameter is for tests to inject a fake sleep function.
    """
    sleep_fn = sleep if callable(sleep) else time.sleep
    backoff = settings.dns_check_backoff_sec
    max_attempts = settings.dns_check_max_attempts
    resolvers = settings.dns_check_resolvers
    timeout = settings.dns_check_timeout_sec

    start = time.monotonic()
    last_error: str | None = None
    resolvers_seen: list[str] = []
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        found_in: list[str] = []
        errors: list[str] = []

        for resolver_ip in resolvers:
            try:
                values = _query_txt(domain, resolver_ip, timeout)
                if any(expected_token in v for v in values):
                    found_in.append(resolver_ip)
            except (dns.exception.DNSException, OSError) as e:
                errors.append(f"{resolver_ip}: {e}")

        for r in found_in:
            if r not in resolvers_seen:
                resolvers_seen.append(r)

        if found_in:
            return DnsCheckResult(
                propagated=True,
                attempts=attempts,
                elapsed_sec=time.monotonic() - start,
                last_error=None,
                resolvers_seen=resolvers_seen,
            )

        last_error = "; ".join(errors) if errors else "TXT record not found"

        if attempt < max_attempts:
            delay = backoff[min(attempt - 1, len(backoff) - 1)]
            sleep_fn(delay)

    return DnsCheckResult(
        propagated=False,
        attempts=attempts,
        elapsed_sec=time.monotonic() - start,
        last_error=last_error,
        resolvers_seen=resolvers_seen,
    )


def _query_txt(domain: str, resolver_ip: str, timeout: float) -> list[str]:
    """Query a single resolver for TXT records of `domain`. Returns concatenated string values."""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [resolver_ip]
    resolver.timeout = timeout
    resolver.lifetime = timeout
    answer = resolver.resolve(domain, "TXT")

    values: list[str] = []
    for rdata in answer:
        parts = [s.decode("utf-8") if isinstance(s, bytes) else str(s) for s in rdata.strings]
        values.append("".join(parts))
    return values
