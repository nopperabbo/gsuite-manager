"""Unit tests for clients/mx_check.py with mocked DNS resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import dns.exception
import dns.resolver
import pytest

from gsm.clients.mx_check import (
    EXPECTED_GOOGLE_MX,
    MxCheckResult,
    MxRecord,
    MxStatus,
    _detect_provider,
    check_mx,
)
from gsm.core.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        cf_api_token="t",
        cf_account_id="0061a056f8cbc860fb9ec99bd41a0ccc",
        google_oauth_client_path=tmp_path / "credentials.json",
        google_oauth_token_path=tmp_path / "token.json",
        ledger_path=tmp_path / "gsm_state.json",
        dns_check_resolvers=["8.8.8.8", "1.1.1.1"],
        dns_check_timeout_sec=2.0,
        dns_check_max_attempts=3,
        dns_check_backoff_sec=[5, 10, 15],
    )


def _mk_rdata(host: str, priority: int) -> MagicMock:
    rdata = MagicMock()
    rdata.exchange = MagicMock()
    rdata.exchange.__str__ = MagicMock(return_value=f"{host}.")
    rdata.preference = priority
    return rdata


def _all_google_records() -> list[MagicMock]:
    return [_mk_rdata(host, prio) for host, prio in EXPECTED_GOOGLE_MX]


class TestMxRecord:
    def test_normalize_lowercase(self) -> None:
        r = MxRecord(host="ASPMX.L.GOOGLE.COM", priority=1)
        assert r.normalized_host() == "aspmx.l.google.com"

    def test_normalize_strip_trailing_dot(self) -> None:
        r = MxRecord(host="aspmx.l.google.com.", priority=1)
        assert r.normalized_host() == "aspmx.l.google.com"


class TestCheckMxHealthy:
    def test_all_google_records_present(self, settings) -> None:
        records = _all_google_records()
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.is_healthy
        assert result.status is MxStatus.HEALTHY
        assert result.detected_provider == "Google Workspace"
        assert len(result.actual_records) == 5
        assert result.missing_records == ()
        assert result.extra_records == ()

    def test_extra_records_still_healthy_with_warning(self, settings) -> None:
        records = [*_all_google_records(), _mk_rdata("backup.example.com", 20)]
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.is_healthy
        assert result.status is MxStatus.HEALTHY
        assert len(result.extra_records) == 1
        assert any("MX tambahan" in d for d in result.diagnostics)


class TestCheckMxPartial:
    def test_missing_some_records(self, settings) -> None:
        records = [
            _mk_rdata("aspmx.l.google.com", 1),
            _mk_rdata("alt1.aspmx.l.google.com", 5),
        ]
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert not result.is_healthy
        assert result.status is MxStatus.PARTIAL
        assert len(result.missing_records) == 3
        assert any("re-inject" in d for d in result.diagnostics)

    def test_wrong_priority_classified_with_diagnostic(self, settings) -> None:
        """Hosts Google tapi priority salah: hosts cocok jadi terdeteksi sebagai Google,
        tapi priority mismatch -> classified PARTIAL with helpful diagnostic.
        """
        records = [_mk_rdata(host, 99) for host, _ in EXPECTED_GOOGLE_MX]
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.status is MxStatus.PARTIAL
        assert any("priority" in d.lower() for d in result.diagnostics)
        assert result.detected_provider == "Google Workspace"


class TestCheckMxNotGoogle:
    def test_outlook_detected(self, settings) -> None:
        records = [
            _mk_rdata("bunhe-tech.mail.protection.outlook.com", 0),
        ]
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.status is MxStatus.NOT_GOOGLE
        assert result.detected_provider == "Microsoft 365 / Outlook"

    def test_zoho_detected(self, settings) -> None:
        records = [_mk_rdata("mx.zoho.com", 10)]
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.status is MxStatus.NOT_GOOGLE
        assert result.detected_provider == "Zoho Mail"

    def test_unknown_provider_returns_host(self, settings) -> None:
        records = [_mk_rdata("mail.weirdmail.example", 10)]
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.status is MxStatus.NOT_GOOGLE
        assert result.detected_provider == "mail.weirdmail.example"


class TestCheckMxNoMx:
    def test_no_answer_returns_no_mx(self, settings) -> None:
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.side_effect = dns.resolver.NoAnswer()
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.status is MxStatus.NO_MX
        assert any("MX record" in d for d in result.diagnostics)


class TestCheckMxError:
    def test_nxdomain_all_resolvers_returns_error(self, settings) -> None:
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.side_effect = dns.resolver.NXDOMAIN()
            resolver_cls.return_value = instance
            result = check_mx("nonexistent-domain-xyz.invalid", settings)

        assert result.status is MxStatus.ERROR
        assert "NXDOMAIN" in (result.error or "")

    def test_timeout_returns_error(self, settings) -> None:
        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.side_effect = dns.exception.Timeout()
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.status is MxStatus.ERROR

    def test_empty_domain_returns_error(self, settings) -> None:
        result = check_mx("", settings)
        assert result.status is MxStatus.ERROR
        assert "empty domain" in (result.error or "")

    def test_whitespace_domain_returns_error(self, settings) -> None:
        result = check_mx("   ", settings)
        assert result.status is MxStatus.ERROR


class TestCheckMxAggregation:
    def test_partial_response_across_resolvers(self, settings) -> None:
        """If first resolver returns nothing but second returns Google MX, classify based on aggregated."""
        call_count = {"n": 0}

        def resolve_mock(domain, rrtype):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise dns.exception.Timeout()
            return _all_google_records()

        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.side_effect = resolve_mock
            resolver_cls.return_value = instance
            result = check_mx("bunhe.tech", settings)

        assert result.status is MxStatus.HEALTHY


class TestRenderSummary:
    def test_healthy_summary(self) -> None:
        result = MxCheckResult(
            domain="x.com",
            status=MxStatus.HEALTHY,
            actual_records=tuple(MxRecord(h, p) for h, p in EXPECTED_GOOGLE_MX),
            missing_records=(),
            extra_records=(),
            detected_provider="Google Workspace",
            resolvers_consulted=("8.8.8.8",),
        )
        assert "HEALTHY" in result.render_summary()
        assert "5/5" in result.render_summary()

    def test_partial_summary(self) -> None:
        result = MxCheckResult(
            domain="x.com",
            status=MxStatus.PARTIAL,
            actual_records=(MxRecord("aspmx.l.google.com", 1),),
            missing_records=(("alt1.aspmx.l.google.com", 5),),
            extra_records=(),
            detected_provider=None,
            resolvers_consulted=("8.8.8.8",),
        )
        summary = result.render_summary()
        assert "PARTIAL" in summary
        assert "missing" in summary

    def test_not_google_summary(self) -> None:
        result = MxCheckResult(
            domain="x.com",
            status=MxStatus.NOT_GOOGLE,
            actual_records=(MxRecord("mail.outlook.com", 10),),
            missing_records=tuple(EXPECTED_GOOGLE_MX),
            extra_records=(MxRecord("mail.outlook.com", 10),),
            detected_provider="Microsoft 365 / Outlook",
            resolvers_consulted=("8.8.8.8",),
        )
        assert "NOT_GOOGLE" in result.render_summary()
        assert "Outlook" in result.render_summary()

    def test_error_summary(self) -> None:
        result = MxCheckResult(
            domain="x.com",
            status=MxStatus.ERROR,
            actual_records=(),
            missing_records=tuple(EXPECTED_GOOGLE_MX),
            extra_records=(),
            detected_provider=None,
            resolvers_consulted=(),
            error="NXDOMAIN",
        )
        assert "ERROR" in result.render_summary()
        assert "NXDOMAIN" in result.render_summary()


class TestDetectProvider:
    def test_known_provider(self) -> None:
        assert (
            _detect_provider([MxRecord("smtp-in.protection.outlook.com", 0)])
            == "Microsoft 365 / Outlook"
        )

    def test_cloudflare_email_routing(self) -> None:
        assert (
            _detect_provider([MxRecord("isaac.mx.cloudflare.net", 5)]) == "Cloudflare Email Routing"
        )

    def test_no_records_returns_none(self) -> None:
        assert _detect_provider([]) is None

    def test_unknown_falls_back_to_host(self) -> None:
        result = _detect_provider([MxRecord("mail.someweirdprovider.io", 10)])
        assert result == "mail.someweirdprovider.io"
