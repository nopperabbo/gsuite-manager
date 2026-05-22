"""Integration test for workflows/domain_onboarding.py with mocked clients."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gsm.clients.cloudflare import CloudflareError, ZoneInfo
from gsm.clients.dns_check import DnsCheckResult
from gsm.clients.google_admin import GoogleAdminError
from gsm.clients.google_verify import GoogleVerifyError
from gsm.core.config import Settings
from gsm.models.domain import DomainStatus
from gsm.models.results import ResultKind
from gsm.state.ledger import Ledger
from gsm.workflows.domain_onboarding import DomainOnboarder, onboard_domains


@pytest.fixture
def settings(tmp_path):
    return Settings(
        cf_api_token="t",
        cf_account_id="0061a056f8cbc860fb9ec99bd41a0ccc",
        google_oauth_client_path=tmp_path / "credentials.json",
        google_oauth_token_path=tmp_path / "token.json",
        ledger_path=tmp_path / "gsm_state.json",
        dns_check_resolvers=["8.8.8.8"],
        dns_check_max_attempts=2,
        dns_check_backoff_sec=[1],
        delay_per_domain_sec=0.0,
    )


@pytest.fixture
def ledger(settings):
    return Ledger(settings.ledger_path)


@pytest.fixture
def mock_clients():
    cf = MagicMock()
    admin = MagicMock()
    verify = MagicMock()

    cf.ensure_zone.return_value = ZoneInfo(
        zone_id="z-1",
        name="example.com",
        nameservers=["ns1.cf.com", "ns2.cf.com"],
        created=True,
    )
    cf.upsert_dns_record.return_value = True
    admin.add_domain.return_value = True
    verify.get_dns_txt_token.return_value = "google-site-verification=tok-123"
    verify.verify_domain.return_value = True

    return cf, admin, verify


def _ok_dns():
    return DnsCheckResult(
        propagated=True,
        attempts=1,
        elapsed_sec=0.1,
        last_error=None,
        resolvers_seen=["8.8.8.8"],
    )


def _failed_dns():
    return DnsCheckResult(
        propagated=False,
        attempts=2,
        elapsed_sec=15.0,
        last_error="NXDOMAIN",
        resolvers_seen=[],
    )


class TestHappyPath:
    def test_full_onboarding_succeeds(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_ok_dns(),
        ):
            onboarder = DomainOnboarder(
                settings=settings,
                ledger=ledger,
                cf=cf,
                admin=admin,
                verify=verify,
            )
            result = onboarder.run("example.com")

        assert result.kind is ResultKind.SUCCESS
        record = ledger.get_domain("example.com")
        assert record is not None
        assert record.status is DomainStatus.VERIFIED
        assert record.cf_zone_id == "z-1"
        assert record.txt_token == "google-site-verification=tok-123"
        admin.add_domain.assert_called_once_with("example.com")
        cf.ensure_zone.assert_called_once_with("example.com")
        # 5 MX + 1 TXT = 6 DNS upserts
        assert cf.upsert_dns_record.call_count == 6
        verify.verify_domain.assert_called_once_with("example.com")


class TestIdempotency:
    def test_skip_already_verified(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        from gsm.models.domain import DomainRecord

        ledger.upsert_domain(DomainRecord(name="done.com", status=DomainStatus.VERIFIED))

        onboarder = DomainOnboarder(
            settings=settings,
            ledger=ledger,
            cf=cf,
            admin=admin,
            verify=verify,
        )
        result = onboarder.run("done.com")
        assert result.kind is ResultKind.SKIPPED
        admin.add_domain.assert_not_called()
        cf.ensure_zone.assert_not_called()


class TestDnsRaceCondition:
    """Verifies the fix for production bug: 271 verifications failed because
    Google was queried before DNS propagated. We now poll DNS first, return
    PARTIAL if it never propagates within max attempts.
    """

    def test_dns_not_propagated_returns_partial(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_failed_dns(),
        ):
            onboarder = DomainOnboarder(
                settings=settings,
                ledger=ledger,
                cf=cf,
                admin=admin,
                verify=verify,
            )
            result = onboarder.run("slow.com")

        assert result.kind is ResultKind.PARTIAL
        assert "DNS not yet propagated" in result.message
        record = ledger.get_domain("slow.com")
        assert record is not None
        assert record.status is DomainStatus.DNS_PENDING
        verify.verify_domain.assert_not_called()

    def test_retry_after_dns_pending_completes(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients

        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_failed_dns(),
        ):
            onboarder = DomainOnboarder(
                settings=settings,
                ledger=ledger,
                cf=cf,
                admin=admin,
                verify=verify,
            )
            r1 = onboarder.run("retry.com")
        assert r1.kind is ResultKind.PARTIAL

        cf.ensure_zone.reset_mock()
        admin.add_domain.reset_mock()
        verify.get_dns_txt_token.reset_mock()
        verify.verify_domain.reset_mock()

        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_ok_dns(),
        ):
            r2 = onboarder.run("retry.com")
        assert r2.kind is ResultKind.SUCCESS

        admin.add_domain.assert_not_called()
        verify.get_dns_txt_token.assert_not_called()
        verify.verify_domain.assert_called_once()


class TestErrorPaths:
    def test_admin_error_is_failed_result(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        admin.add_domain.side_effect = GoogleAdminError("403 forbidden")

        onboarder = DomainOnboarder(
            settings=settings,
            ledger=ledger,
            cf=cf,
            admin=admin,
            verify=verify,
        )
        result = onboarder.run("forbidden.com")
        assert result.kind is ResultKind.FAILED
        assert "403 forbidden" in result.message

    def test_cloudflare_error_is_failed_result(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        cf.ensure_zone.side_effect = CloudflareError("rate limited")

        onboarder = DomainOnboarder(
            settings=settings,
            ledger=ledger,
            cf=cf,
            admin=admin,
            verify=verify,
        )
        result = onboarder.run("ratelimited.com")
        assert result.kind is ResultKind.FAILED
        assert "rate limit" in result.message.lower()

    def test_verify_error_is_failed_result(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_ok_dns(),
        ):
            verify.verify_domain.side_effect = GoogleVerifyError("token mismatch")
            onboarder = DomainOnboarder(
                settings=settings,
                ledger=ledger,
                cf=cf,
                admin=admin,
                verify=verify,
            )
            result = onboarder.run("verify-fail.com")
        assert result.kind is ResultKind.FAILED


class TestBatchOnboarding:
    def test_batch_processes_all_domains(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_ok_dns(),
        ):
            results = onboard_domains(
                ["a.com", "b.com", "c.com"],
                settings=settings,
                ledger=ledger,
                cf=cf,
                admin=admin,
                verify=verify,
                delay_per_domain_sec=0.0,
            )
        assert len(results) == 3
        assert all(r.kind is ResultKind.SUCCESS for r in results)
        assert admin.add_domain.call_count == 3


class TestEmailRoutingHandling:
    def test_disables_email_routing_before_mx_inject(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        cf.get_email_routing_status.return_value = True

        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_ok_dns(),
        ):
            onboarder = DomainOnboarder(
                settings=settings,
                ledger=ledger,
                cf=cf,
                admin=admin,
                verify=verify,
            )
            result = onboarder.run("with-email-routing.com")

        assert result.kind is ResultKind.SUCCESS
        cf.disable_email_routing.assert_called_once_with("z-1")
        assert cf.upsert_dns_record.call_count >= 5

    def test_skips_disable_when_routing_off(self, settings, ledger, mock_clients):
        cf, admin, verify = mock_clients
        cf.get_email_routing_status.return_value = False

        with patch(
            "gsm.workflows.domain_onboarding.wait_for_txt",
            return_value=_ok_dns(),
        ):
            onboarder = DomainOnboarder(
                settings=settings,
                ledger=ledger,
                cf=cf,
                admin=admin,
                verify=verify,
            )
            onboarder.run("no-email-routing.com")

        cf.disable_email_routing.assert_not_called()


class TestPreflight:
    """`_preflight_domain` rejects bad inputs before any API call."""

    def test_valid_domain_passes(self):
        from gsm.workflows.domain_onboarding import _preflight_domain

        assert _preflight_domain("example.com") is None
        assert _preflight_domain("sub.example.co.id") is None

    def test_empty_rejected(self):
        from gsm.workflows.domain_onboarding import _preflight_domain

        assert _preflight_domain("") is not None
        assert _preflight_domain("   ") is not None

    def test_uppercase_rejected_with_suggestion(self):
        from gsm.workflows.domain_onboarding import _preflight_domain

        result = _preflight_domain("Example.com")
        assert result is not None
        assert "example.com" in result

    def test_whitespace_rejected(self):
        from gsm.workflows.domain_onboarding import _preflight_domain

        assert _preflight_domain("  example.com  ") is not None

    def test_no_tld_rejected(self):
        from gsm.workflows.domain_onboarding import _preflight_domain

        assert _preflight_domain("example") is not None

    def test_url_with_protocol_rejected(self):
        from gsm.workflows.domain_onboarding import _preflight_domain

        assert _preflight_domain("https://example.com") is not None

    def test_www_prefix_warned(self):
        from gsm.workflows.domain_onboarding import _preflight_domain

        result = _preflight_domain("www.example.com")
        assert result is not None
        assert "www" in result.lower() or "apex" in result.lower()
