"""Unit tests for clients/dns_check.py with mocked DNS resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import dns.exception
import pytest

from gsm.clients.dns_check import wait_for_txt
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


def _mk_rdata(strings):
    rdata = MagicMock()
    rdata.strings = strings
    return rdata


def test_propagated_on_first_try(settings):
    fake_answer = [_mk_rdata([b"google-site-verification=expected-token"])]

    def fake_resolve(domain, rrtype):
        return fake_answer

    sleeps: list[float] = []

    def fake_sleep(d):
        sleeps.append(d)

    with patch("dns.resolver.Resolver") as resolver_cls:
        instance = MagicMock()
        instance.resolve = fake_resolve
        resolver_cls.return_value = instance

        result = wait_for_txt(
            "example.com",
            "expected-token",
            settings,
            sleep=fake_sleep,
        )
    assert result.propagated is True
    assert result.attempts == 1
    assert "8.8.8.8" in result.resolvers_seen
    assert sleeps == []


def test_propagation_retry_then_success(settings):
    call_state = {"count": 0}

    def fake_resolve(domain, rrtype):
        call_state["count"] += 1
        if call_state["count"] <= 2:
            raise dns.exception.DNSException("NXDOMAIN")
        return [_mk_rdata([b"google-site-verification=expected"])]

    sleeps: list[float] = []

    def fake_sleep(d):
        sleeps.append(d)

    with patch("dns.resolver.Resolver") as resolver_cls:
        instance = MagicMock()
        instance.resolve = fake_resolve
        resolver_cls.return_value = instance
        result = wait_for_txt(
            "example.com",
            "expected",
            settings,
            sleep=fake_sleep,
        )

    assert result.propagated is True
    assert result.attempts >= 2
    assert len(sleeps) >= 1
    assert sleeps[0] == 5


def test_max_attempts_exhausted(settings):
    def fake_resolve(domain, rrtype):
        raise dns.exception.DNSException("NXDOMAIN")

    sleeps: list[float] = []

    def fake_sleep(d):
        sleeps.append(d)

    with patch("dns.resolver.Resolver") as resolver_cls:
        instance = MagicMock()
        instance.resolve = fake_resolve
        resolver_cls.return_value = instance
        result = wait_for_txt(
            "example.com",
            "expected",
            settings,
            sleep=fake_sleep,
        )

    assert result.propagated is False
    assert result.attempts == 3
    assert "NXDOMAIN" in (result.last_error or "")
    assert len(sleeps) == 2


def test_token_present_in_other_record_returns_propagated(settings):
    fake_answer = [
        _mk_rdata([b"v=spf1 include:_spf.google.com ~all"]),
        _mk_rdata([b"google-site-verification=expected-token"]),
    ]

    def fake_resolve(domain, rrtype):
        return fake_answer

    with patch("dns.resolver.Resolver") as resolver_cls:
        instance = MagicMock()
        instance.resolve = fake_resolve
        resolver_cls.return_value = instance
        result = wait_for_txt(
            "example.com", "expected-token", settings, sleep=lambda d: None
        )
    assert result.propagated is True


def test_token_not_in_records_keeps_polling(settings):
    fake_answer = [_mk_rdata([b"v=spf1 -all"])]

    def fake_resolve(domain, rrtype):
        return fake_answer

    with patch("dns.resolver.Resolver") as resolver_cls:
        instance = MagicMock()
        instance.resolve = fake_resolve
        resolver_cls.return_value = instance
        result = wait_for_txt(
            "example.com",
            "needle",
            settings,
            sleep=lambda d: None,
        )
    assert result.propagated is False
    assert "TXT record not found" in (result.last_error or "")
