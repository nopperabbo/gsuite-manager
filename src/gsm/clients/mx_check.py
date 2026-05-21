"""MX record health check for Google Workspace domains.

Validates that a domain's MX records point to Google Workspace mail servers
(ASPMX.L.GOOGLE.COM + ALT1-4). This is the realistic interpretation of
"is Gmail active for this domain" - because Gmail itself doesn't have a
per-domain enable/disable toggle. If MX is set correctly and DNS has
propagated, Gmail is receiving mail.

Used as a manual sanity check after `gsm domains add` completes:

    gsm domains check-mx bunhe.tech

Returns one of:
    HEALTHY     - all 5 Google MX records present with correct priorities
    PARTIAL     - some Google MX records present, some missing/wrong
    NOT_GOOGLE  - MX exists but points to a different mail provider
    NO_MX       - domain has no MX records at all
    ERROR       - DNS lookup failed (NXDOMAIN, timeout, etc)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import dns.exception
import dns.resolver

from gsm.core.config import Settings
from gsm.core.logging import get_logger

__all__ = ["EXPECTED_GOOGLE_MX", "MxCheckResult", "MxRecord", "MxStatus", "check_mx"]

# Expected Google Workspace MX records (host, priority).
# Source: https://support.google.com/a/answer/174125
EXPECTED_GOOGLE_MX: tuple[tuple[str, int], ...] = (
    ("aspmx.l.google.com", 1),
    ("alt1.aspmx.l.google.com", 5),
    ("alt2.aspmx.l.google.com", 5),
    ("alt3.aspmx.l.google.com", 10),
    ("alt4.aspmx.l.google.com", 10),
)

# Common non-Google mail providers, for friendly diagnostics.
# Format: substring -> human label
_KNOWN_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("outlook.com", "Microsoft 365 / Outlook"),
    ("protection.outlook.com", "Microsoft 365 / Outlook"),
    ("zoho", "Zoho Mail"),
    ("yandex", "Yandex Mail"),
    ("mailgun", "Mailgun"),
    ("amazonses.com", "Amazon SES"),
    ("amazonaws.com", "Amazon SES"),
    ("mxhichina.com", "Alibaba Mail"),
    ("qq.com", "Tencent QQ Mail"),
    ("yahoo", "Yahoo Mail"),
    ("mailbox.org", "Mailbox.org"),
    ("fastmail", "FastMail"),
    ("titan.email", "Titan / Hostinger"),
    ("forwardemail.net", "ForwardEmail.net"),
    ("improvmx", "ImprovMX"),
    ("mx.cloudflare.net", "Cloudflare Email Routing"),
    ("registrar-servers.com", "Namecheap default"),
)

_log = get_logger("clients.mx_check")


class MxStatus(StrEnum):
    HEALTHY = "healthy"
    PARTIAL = "partial"
    NOT_GOOGLE = "not_google"
    NO_MX = "no_mx"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class MxRecord:
    """A single MX record observation."""

    host: str
    priority: int

    def normalized_host(self) -> str:
        """Lowercase, strip trailing dot."""
        return self.host.lower().rstrip(".")


@dataclass(frozen=True, slots=True)
class MxCheckResult:
    """Outcome of an MX check for a single domain."""

    domain: str
    status: MxStatus
    actual_records: tuple[MxRecord, ...]
    missing_records: tuple[tuple[str, int], ...]
    extra_records: tuple[MxRecord, ...]
    detected_provider: str | None
    resolvers_consulted: tuple[str, ...]
    error: str | None = None
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_healthy(self) -> bool:
        return self.status is MxStatus.HEALTHY

    def render_summary(self) -> str:
        """One-line human summary, suitable for log/terminal."""
        if self.status is MxStatus.HEALTHY:
            return f"{self.domain}: HEALTHY (5/5 Google MX records present)"
        if self.status is MxStatus.PARTIAL:
            present = len(EXPECTED_GOOGLE_MX) - len(self.missing_records)
            return f"{self.domain}: PARTIAL ({present}/5 Google MX records, {len(self.missing_records)} missing)"
        if self.status is MxStatus.NOT_GOOGLE:
            provider = self.detected_provider or "unknown provider"
            return f"{self.domain}: NOT_GOOGLE (MX points to {provider})"
        if self.status is MxStatus.NO_MX:
            return f"{self.domain}: NO_MX (no MX records configured)"
        return f"{self.domain}: ERROR ({self.error or 'unknown'})"


def check_mx(domain: str, settings: Settings) -> MxCheckResult:
    """Resolve MX records and classify Gmail readiness.

    Queries the resolvers configured in `settings.dns_check_resolvers` (default:
    8.8.8.8 + 1.1.1.1). Aggregates the responses; if any resolver returns
    Google MX records and at least one has a complete answer, classification
    proceeds against that.

    Returns an MxCheckResult; never raises. DNS errors become MxStatus.ERROR.
    """
    if not domain or not domain.strip():
        return MxCheckResult(
            domain=domain,
            status=MxStatus.ERROR,
            actual_records=(),
            missing_records=tuple(EXPECTED_GOOGLE_MX),
            extra_records=(),
            detected_provider=None,
            resolvers_consulted=(),
            error="empty domain",
        )

    domain_norm = domain.strip().lower()
    resolvers = settings.dns_check_resolvers
    timeout = settings.dns_check_timeout_sec

    aggregated: list[MxRecord] = []
    consulted: list[str] = []
    last_error: str | None = None
    nxdomain_count = 0
    no_answer_count = 0

    for resolver_ip in resolvers:
        try:
            records = _query_mx(domain_norm, resolver_ip, timeout)
            consulted.append(resolver_ip)
            for r in records:
                if r not in aggregated:
                    aggregated.append(r)
        except dns.resolver.NXDOMAIN as e:
            nxdomain_count += 1
            last_error = f"{resolver_ip}: NXDOMAIN ({e})"
        except dns.resolver.NoAnswer as e:
            no_answer_count += 1
            last_error = f"{resolver_ip}: no MX records ({e})"
            consulted.append(resolver_ip)
        except (dns.exception.DNSException, OSError) as e:
            last_error = f"{resolver_ip}: {e}"

    # All resolvers returned NXDOMAIN -> domain doesn't resolve at all.
    if nxdomain_count == len(resolvers):
        return MxCheckResult(
            domain=domain_norm,
            status=MxStatus.ERROR,
            actual_records=(),
            missing_records=tuple(EXPECTED_GOOGLE_MX),
            extra_records=(),
            detected_provider=None,
            resolvers_consulted=tuple(consulted),
            error=last_error,
        )

    # All resolvers returned NoAnswer -> domain resolves but has no MX.
    if no_answer_count > 0 and not aggregated:
        return MxCheckResult(
            domain=domain_norm,
            status=MxStatus.NO_MX,
            actual_records=(),
            missing_records=tuple(EXPECTED_GOOGLE_MX),
            extra_records=(),
            detected_provider=None,
            resolvers_consulted=tuple(consulted),
            error=None,
            diagnostics=(
                "Domain ada di DNS tapi belum punya MX record. "
                "Run `gsm domains add` untuk inject MX Google.",
            ),
        )

    # Other errors with no aggregated answer.
    if not aggregated:
        return MxCheckResult(
            domain=domain_norm,
            status=MxStatus.ERROR,
            actual_records=(),
            missing_records=tuple(EXPECTED_GOOGLE_MX),
            extra_records=(),
            detected_provider=None,
            resolvers_consulted=tuple(consulted),
            error=last_error or "no resolvers responded",
        )

    return _classify(domain_norm, aggregated, tuple(consulted))


def _classify(
    domain: str,
    actual: list[MxRecord],
    resolvers_consulted: tuple[str, ...],
) -> MxCheckResult:
    """Compare actual records against expected Google MX set."""
    expected_set = {(host.lower(), prio) for host, prio in EXPECTED_GOOGLE_MX}
    expected_hosts = {host.lower() for host, _ in EXPECTED_GOOGLE_MX}
    actual_normalized = {(r.normalized_host(), r.priority) for r in actual}
    actual_hosts = {r.normalized_host() for r in actual}

    matched = actual_normalized & expected_set
    missing = expected_set - actual_normalized
    extra = [r for r in actual if (r.normalized_host(), r.priority) not in expected_set]

    diagnostics: list[str] = []

    # All Google MX present and no extras -> HEALTHY
    if not missing and not extra:
        _log.info("mx_check_healthy", domain=domain, records=len(actual))
        return MxCheckResult(
            domain=domain,
            status=MxStatus.HEALTHY,
            actual_records=tuple(actual),
            missing_records=(),
            extra_records=(),
            detected_provider="Google Workspace",
            resolvers_consulted=resolvers_consulted,
            diagnostics=tuple(diagnostics),
        )

    # All Google MX present but with extras -> still HEALTHY for receiving,
    # but warn about extras.
    if not missing and extra:
        diagnostics.append(
            f"Ada {len(extra)} MX tambahan di luar set Google. "
            "Cek apakah ini intentional (mis. backup MX) atau sisa config lama."
        )
        _log.warning(
            "mx_check_healthy_with_extras",
            domain=domain,
            extra_count=len(extra),
        )
        return MxCheckResult(
            domain=domain,
            status=MxStatus.HEALTHY,
            actual_records=tuple(actual),
            missing_records=(),
            extra_records=tuple(extra),
            detected_provider="Google Workspace",
            resolvers_consulted=resolvers_consulted,
            diagnostics=tuple(diagnostics),
        )

    # Detect wrong-priority case: hosts are Google but priorities don't match.
    # Classify as PARTIAL with explicit diagnostic so user knows what's wrong.
    google_hosts_present = actual_hosts & expected_hosts
    if google_hosts_present and not matched:
        diagnostics.append(
            "Hosts MX cocok dengan Google tapi priority salah. "
            "Run `gsm domains add <domain>` untuk fix priority (idempotent)."
        )
        _log.warning(
            "mx_check_wrong_priority",
            domain=domain,
            google_hosts=len(google_hosts_present),
        )
        return MxCheckResult(
            domain=domain,
            status=MxStatus.PARTIAL,
            actual_records=tuple(actual),
            missing_records=tuple(sorted(missing, key=lambda x: (x[1], x[0]))),
            extra_records=tuple(extra),
            detected_provider="Google Workspace",
            resolvers_consulted=resolvers_consulted,
            diagnostics=tuple(diagnostics),
        )

    # Some Google MX records present (correct host+priority) but not all -> PARTIAL
    if matched and missing:
        diagnostics.append(
            f"{len(missing)} MX Google missing. "
            "Run `gsm domains add <domain>` untuk re-inject (idempotent)."
        )
        if extra:
            provider = _detect_provider(extra)
            if provider:
                diagnostics.append(
                    f"Selain itu, ada MX yang nunjuk ke {provider}. Mungkin perlu di-clean up."
                )
        _log.warning(
            "mx_check_partial",
            domain=domain,
            matched=len(matched),
            missing=len(missing),
        )
        return MxCheckResult(
            domain=domain,
            status=MxStatus.PARTIAL,
            actual_records=tuple(actual),
            missing_records=tuple(sorted(missing, key=lambda x: (x[1], x[0]))),
            extra_records=tuple(extra),
            detected_provider=_detect_provider(extra),
            resolvers_consulted=resolvers_consulted,
            diagnostics=tuple(diagnostics),
        )

    # No Google hosts matched at all -> NOT_GOOGLE
    provider = _detect_provider(actual)
    diagnostics.append(
        "Domain ini punya MX, tapi bukan ke Google. "
        "Kalo lo mau pindah ke Google Workspace, "
        "run `gsm domains add <domain>` (akan replace MX existing)."
    )
    _log.warning(
        "mx_check_not_google",
        domain=domain,
        provider=provider,
        record_count=len(actual),
    )
    return MxCheckResult(
        domain=domain,
        status=MxStatus.NOT_GOOGLE,
        actual_records=tuple(actual),
        missing_records=tuple(EXPECTED_GOOGLE_MX),
        extra_records=tuple(actual),
        detected_provider=provider,
        resolvers_consulted=resolvers_consulted,
        diagnostics=tuple(diagnostics),
    )


def _detect_provider(records: list[MxRecord] | tuple[MxRecord, ...]) -> str | None:
    """Best-effort identification of mail provider from MX hostnames."""
    for record in records:
        host = record.normalized_host()
        for needle, label in _KNOWN_PROVIDERS:
            if needle in host:
                return label
    if records:
        # Unknown but there is at least one MX; show the host so user
        # can investigate.
        return records[0].normalized_host()
    return None


def _query_mx(domain: str, resolver_ip: str, timeout: float) -> list[MxRecord]:
    """Query a single resolver for MX records of `domain`."""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [resolver_ip]
    resolver.timeout = timeout
    resolver.lifetime = timeout
    answer = resolver.resolve(domain, "MX")

    records: list[MxRecord] = []
    for rdata in answer:
        # rdata.exchange is a dns.name.Name; rdata.preference is int
        host = str(rdata.exchange).rstrip(".")
        priority = int(rdata.preference)
        records.append(MxRecord(host=host, priority=priority))
    return records
