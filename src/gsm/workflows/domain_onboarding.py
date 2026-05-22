"""Domain onboarding workflow.

Orchestrates the full domain onboarding sequence with idempotency and DNS pre-check:

  1. Add domain to Workspace (skip if already added)
  2. Fetch DNS_TXT verification token from Google
  3. Ensure Cloudflare zone exists (create or fetch)
  4. Inject MX records (Google Workspace) + TXT verification record
  5. Wait for TXT to propagate via dnspython poll (8.8.8.8 + 1.1.1.1)
  6. Trigger Google verify
  7. Persist state to ledger after each step

Idempotency: re-running on a domain at any partial state will pick up where
it left off based on ledger status. The DNS pre-check (step 5) eliminates the
race condition that caused 271 verification failures in legacy script.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime

from gsm.clients.cloudflare import CloudflareClient, CloudflareError
from gsm.clients.dns_check import DnsCheckResult, wait_for_txt
from gsm.clients.google_admin import GoogleAdminClient, GoogleAdminError
from gsm.clients.google_verify import GoogleVerifyClient, GoogleVerifyError
from gsm.core.auth import AuthError
from gsm.core.config import Settings
from gsm.core.errors import humanize
from gsm.core.logging import get_logger
from gsm.models.constants import GOOGLE_MX_RECORDS
from gsm.models.domain import DomainRecord, DomainStatus
from gsm.models.results import ItemResult
from gsm.state.ledger import Ledger

__all__ = ["DomainOnboarder", "onboard_domains"]


class DomainOnboarder:
    """Stateful onboarding executor: pass injected dependencies, call .run(domain)."""

    def __init__(
        self,
        *,
        settings: Settings,
        ledger: Ledger,
        cf: CloudflareClient,
        admin: GoogleAdminClient,
        verify: GoogleVerifyClient,
    ) -> None:
        self._settings = settings
        self._ledger = ledger
        self._cf = cf
        self._admin = admin
        self._verify = verify
        self._log = get_logger("workflow.domain_onboarding")

    def run(self, domain: str) -> ItemResult:
        """Execute the full onboarding pipeline for a single domain.

        Returns ItemResult: success/skipped/partial/failed plus details
        (zone_id, nameservers, dns propagation stats).
        """
        preflight_error = _preflight_domain(domain)
        if preflight_error is not None:
            return ItemResult.failed(domain, preflight_error)

        record = self._ledger.get_domain(domain) or DomainRecord(
            name=domain,
            status=DomainStatus.PENDING,
        )

        if record.status is DomainStatus.VERIFIED:
            self._log.info("domain_already_verified", domain=domain)
            return ItemResult.skipped(domain, "already verified", status=record.status.value)

        try:
            self._step_add_to_gsuite(record)
            token = self._step_fetch_token(record)
            zone_info = self._step_ensure_cf_zone(record)
            self._step_inject_dns(record, zone_info.zone_id, token)
            dns_result = self._step_wait_for_dns(record, token)

            if not dns_result.propagated:
                record.last_error = (
                    f"dns not propagated after {dns_result.attempts} attempts: "
                    f"{dns_result.last_error}"
                )
                record.status = DomainStatus.DNS_PENDING
                self._save(record)
                return ItemResult.partial(
                    domain,
                    f"DNS not yet propagated ({dns_result.attempts} attempts, "
                    f"{dns_result.elapsed_sec:.1f}s)",
                    status=record.status.value,
                    zone_id=record.cf_zone_id,
                    nameservers=record.cf_nameservers,
                    attempts=dns_result.attempts,
                )

            self._step_verify(record)
            return ItemResult.success(
                domain,
                "verified",
                status=record.status.value,
                zone_id=record.cf_zone_id,
                nameservers=record.cf_nameservers,
                dns_attempts=dns_result.attempts,
            )

        except (
            AuthError,
            GoogleAdminError,
            GoogleVerifyError,
            CloudflareError,
        ) as e:
            record.last_error = str(e)
            if record.status is DomainStatus.PENDING:
                record.status = DomainStatus.FAILED
            self._save(record)
            self._log.error(
                "domain_step_failed",
                domain=domain,
                status=record.status.value,
                error=str(e),
            )
            return ItemResult.failed(domain, humanize(e).render(), status=record.status.value)

    def _step_add_to_gsuite(self, record: DomainRecord) -> None:
        if record.status not in (
            DomainStatus.PENDING,
            DomainStatus.FAILED,
        ):
            return
        self._log.info("step_add_gsuite", domain=record.name)
        self._admin.add_domain(record.name)
        record.status = DomainStatus.GSUITE_ADDED
        self._save(record)

    def _step_fetch_token(self, record: DomainRecord) -> str:
        if record.txt_token and record.status in (
            DomainStatus.TOKEN_FETCHED,
            DomainStatus.CF_ZONE_READY,
            DomainStatus.DNS_INJECTED,
            DomainStatus.DNS_PENDING,
        ):
            return record.txt_token
        self._log.info("step_fetch_token", domain=record.name)
        token = self._verify.get_dns_txt_token(record.name)
        record.txt_token = token
        record.status = DomainStatus.TOKEN_FETCHED
        self._save(record)
        return token

    def _step_ensure_cf_zone(self, record: DomainRecord) -> _ZoneSnapshot:
        self._log.info("step_ensure_zone", domain=record.name)
        zone = self._cf.ensure_zone(record.name)
        record.cf_zone_id = zone.zone_id
        record.cf_nameservers = list(zone.nameservers)
        if record.status in (
            DomainStatus.GSUITE_ADDED,
            DomainStatus.TOKEN_FETCHED,
        ):
            record.status = DomainStatus.CF_ZONE_READY
        self._save(record)
        return _ZoneSnapshot(zone.zone_id, list(zone.nameservers))

    def _step_inject_dns(self, record: DomainRecord, zone_id: str, token: str) -> None:
        if record.status is DomainStatus.DNS_INJECTED or record.status is DomainStatus.DNS_PENDING:
            return
        self._log.info("step_inject_dns", domain=record.name, zone_id=zone_id)

        if self._cf.get_email_routing_status(zone_id):
            self._log.info(
                "disabling_email_routing",
                domain=record.name,
                zone_id=zone_id,
                reason="blocks_workspace_mx",
            )
            self._cf.disable_email_routing(zone_id)

        for mx in GOOGLE_MX_RECORDS:
            self._cf.upsert_dns_record(
                zone_id,
                record_type="MX",
                name=record.name,
                content=mx["content"],  # type: ignore[arg-type]
                priority=mx["priority"],  # type: ignore[arg-type]
            )
        self._cf.upsert_dns_record(
            zone_id,
            record_type="TXT",
            name=record.name,
            content=token,
        )
        record.status = DomainStatus.DNS_INJECTED
        self._save(record)

    def _step_wait_for_dns(self, record: DomainRecord, token: str) -> DnsCheckResult:
        self._log.info("step_wait_dns", domain=record.name)
        result = wait_for_txt(record.name, token, self._settings)
        self._log.info(
            "dns_check_result",
            domain=record.name,
            propagated=result.propagated,
            attempts=result.attempts,
            elapsed_sec=round(result.elapsed_sec, 2),
            resolvers_seen=result.resolvers_seen,
        )
        return result

    def _step_verify(self, record: DomainRecord) -> None:
        self._log.info("step_verify", domain=record.name)
        self._verify.verify_domain(record.name)
        record.status = DomainStatus.VERIFIED
        record.last_error = None
        self._save(record)

    def _save(self, record: DomainRecord) -> None:
        record.last_updated = datetime.now(UTC)
        self._ledger.upsert_domain(record)


class _ZoneSnapshot:
    __slots__ = ("nameservers", "zone_id")

    def __init__(self, zone_id: str, nameservers: list[str]) -> None:
        self.zone_id = zone_id
        self.nameservers = nameservers


def onboard_domains(
    domains: list[str],
    *,
    settings: Settings,
    ledger: Ledger,
    cf: CloudflareClient,
    admin: GoogleAdminClient,
    verify: GoogleVerifyClient,
    delay_per_domain_sec: float | None = None,
    on_progress: Callable[[int, int, str, ItemResult], None] | None = None,
) -> list[ItemResult]:
    """Sequential batch onboarding. Sleeps between domains by configured delay.

    on_progress(index, total, domain, result) called after each domain completes.
    """
    onboarder = DomainOnboarder(settings=settings, ledger=ledger, cf=cf, admin=admin, verify=verify)
    delay = (
        delay_per_domain_sec if delay_per_domain_sec is not None else settings.delay_per_domain_sec
    )
    results: list[ItemResult] = []
    total = len(domains)
    for idx, domain in enumerate(domains):
        try:
            result = onboarder.run(domain)
        except KeyboardInterrupt:
            break
        results.append(result)
        if on_progress is not None:
            on_progress(idx + 1, total, domain, result)
        if idx < total - 1 and delay > 0:
            try:
                time.sleep(delay)
            except KeyboardInterrupt:
                break
    return results


_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def _preflight_domain(domain: str) -> str | None:
    """Check domain syntax before any API call. Returns error string or None."""
    if not domain or not domain.strip():
        return "Domain kosong."
    normalized = domain.strip().lower()
    if normalized != domain:
        return f"Domain harus huruf kecil tanpa whitespace. Gunakan: {normalized}"
    if not _DOMAIN_RE.match(domain):
        return "Format domain tidak valid. Contoh benar: 'example.com', 'sub.example.co.id'."
    if domain.startswith(("xn--", "www.")):
        return (
            f"Domain '{domain}' kelihatan unusual "
            "(IDN punycode atau prefix www). "
            "Pastikan ini domain apex (root), bukan subdomain."
        )
    return None
