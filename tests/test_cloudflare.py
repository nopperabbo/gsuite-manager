"""Unit tests for clients/cloudflare.py with mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gsm.clients.cloudflare import CloudflareClient, CloudflareError
from gsm.core.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        cf_api_token="dummy-token",
        cf_account_id="0061a056f8cbc860fb9ec99bd41a0ccc",
        google_oauth_client_path=tmp_path / "credentials.json",
        google_oauth_token_path=tmp_path / "token.json",
        ledger_path=tmp_path / "gsm_state.json",
    )


@pytest.fixture
def client(settings):
    return CloudflareClient(settings)


def _ok(zone_id="zone-abc", name="example.com", nameservers=None):
    return {
        "success": True,
        "result": {
            "id": zone_id,
            "name": name,
            "name_servers": nameservers or ["ns1.cf.com", "ns2.cf.com"],
        },
    }


def _err(code: int, message: str = "boom"):
    return {"success": False, "errors": [{"code": code, "message": message}]}


class TestEnsureZone:
    def test_creates_new_zone(self, client):
        post_resp = MagicMock()
        post_resp.json.return_value = _ok()
        get_resp = MagicMock()
        get_resp.json.return_value = {
            "success": True,
            "result": [
                {
                    "id": "zone-abc",
                    "name": "example.com",
                    "name_servers": ["ns1.cf.com", "ns2.cf.com"],
                }
            ],
        }
        with patch.object(
            client._session,
            "request",
            side_effect=[post_resp, get_resp],
        ):
            info = client.ensure_zone("example.com")
        assert info.zone_id == "zone-abc"
        assert info.created is True
        assert info.nameservers == ["ns1.cf.com", "ns2.cf.com"]

    def test_existing_zone_treated_as_success(self, client):
        post_resp = MagicMock()
        post_resp.json.return_value = _err(1061, "zone already exists")
        get_resp = MagicMock()
        get_resp.json.return_value = {
            "success": True,
            "result": [
                {
                    "id": "zone-existing",
                    "name": "example.com",
                    "name_servers": ["a.cf.com"],
                }
            ],
        }
        with patch.object(
            client._session,
            "request",
            side_effect=[post_resp, get_resp],
        ):
            info = client.ensure_zone("example.com")
        assert info.zone_id == "zone-existing"
        assert info.created is False

    def test_unknown_error_raises(self, client):
        post_resp = MagicMock()
        post_resp.json.return_value = _err(9999, "weird error")
        with patch.object(client._session, "request", return_value=post_resp), pytest.raises(CloudflareError) as exc:
            client.ensure_zone("example.com")
        assert "weird error" in str(exc.value)


class TestUpsertDnsRecord:
    def test_creates_new_record(self, client):
        resp = MagicMock()
        resp.json.return_value = {"success": True, "result": {"id": "rec-1"}}
        with patch.object(client._session, "request", return_value=resp):
            ok = client.upsert_dns_record(
                "zone-1",
                record_type="MX",
                name="example.com",
                content="ASPMX.L.GOOGLE.COM",
                priority=1,
            )
        assert ok is True

    def test_already_exists_81057_treated_as_success(self, client):
        resp = MagicMock()
        resp.json.return_value = _err(81057, "record already exists")
        with patch.object(client._session, "request", return_value=resp):
            ok = client.upsert_dns_record(
                "zone-1",
                record_type="TXT",
                name="example.com",
                content="google-site-verification=xxx",
            )
        assert ok is True

    def test_already_exists_81058_treated_as_success(self, client):
        resp = MagicMock()
        resp.json.return_value = _err(81058, "duplicate")
        with patch.object(client._session, "request", return_value=resp):
            assert (
                client.upsert_dns_record(
                    "zone-1",
                    record_type="MX",
                    name="example.com",
                    content="ASPMX.L.GOOGLE.COM",
                    priority=1,
                )
                is True
            )

    def test_unknown_error_raises(self, client):
        resp = MagicMock()
        resp.json.return_value = _err(1234, "permission denied")
        with patch.object(client._session, "request", return_value=resp), pytest.raises(CloudflareError):
            client.upsert_dns_record(
                "zone-1",
                record_type="MX",
                name="example.com",
                content="ASPMX.L.GOOGLE.COM",
                priority=1,
            )


class TestGetZoneByName:
    def test_returns_none_when_not_found(self, client):
        resp = MagicMock()
        resp.json.return_value = {"success": True, "result": []}
        with patch.object(client._session, "request", return_value=resp):
            assert client.get_zone_by_name("nope.com") is None

    def test_returns_zone_info_when_found(self, client):
        resp = MagicMock()
        resp.json.return_value = {
            "success": True,
            "result": [
                {
                    "id": "z1",
                    "name": "found.com",
                    "name_servers": ["a.cf.com"],
                }
            ],
        }
        with patch.object(client._session, "request", return_value=resp):
            info = client.get_zone_by_name("found.com")
        assert info is not None
        assert info.zone_id == "z1"
        assert info.created is False


class TestRequestWrapping:
    """Network-level errors must be wrapped in CloudflareError."""

    def test_timeout_wrapped(self, client):
        import requests

        with patch.object(
            client._session,
            "request",
            side_effect=requests.Timeout("timeout"),
        ), pytest.raises(CloudflareError) as exc:
            client.ensure_zone("example.com")
        assert "network error" in str(exc.value).lower()

    def test_connection_error_wrapped(self, client):
        import requests

        with patch.object(
            client._session,
            "request",
            side_effect=requests.ConnectionError("conn refused"),
        ), pytest.raises(CloudflareError):
            client.ensure_zone("example.com")

    def test_non_json_response_wrapped(self, client):
        bad_resp = MagicMock()
        bad_resp.status_code = 502
        bad_resp.json.side_effect = ValueError("not json")
        with patch.object(
            client._session, "request", return_value=bad_resp
        ), pytest.raises(CloudflareError) as exc:
            client.ensure_zone("example.com")
        assert "non-JSON" in str(exc.value) or "502" in str(exc.value)


class TestEmailRouting:
    def test_get_status_enabled(self, client):
        resp = MagicMock()
        resp.json.return_value = {
            "success": True,
            "result": {"enabled": True, "name": "example.com"},
        }
        with patch.object(client._session, "request", return_value=resp):
            assert client.get_email_routing_status("zone-1") is True

    def test_get_status_disabled(self, client):
        resp = MagicMock()
        resp.json.return_value = {
            "success": True,
            "result": {"enabled": False, "name": "example.com"},
        }
        with patch.object(client._session, "request", return_value=resp):
            assert client.get_email_routing_status("zone-1") is False

    def test_get_status_not_found_returns_none(self, client):
        with patch.object(
            client._session,
            "request",
            side_effect=CloudflareError("404"),
        ):
            assert client.get_email_routing_status("zone-1") is None

    def test_disable_success(self, client):
        resp = MagicMock()
        resp.json.return_value = {
            "success": True,
            "result": {"enabled": False},
        }
        with patch.object(client._session, "request", return_value=resp):
            assert client.disable_email_routing("zone-1") is True

    def test_disable_already_disabled_idempotent(self, client):
        resp = MagicMock()
        resp.json.return_value = {
            "success": False,
            "errors": [{"code": 0, "message": "Email Routing not enabled"}],
        }
        with patch.object(client._session, "request", return_value=resp):
            assert client.disable_email_routing("zone-1") is True

    def test_disable_hard_failure_raises(self, client):
        resp = MagicMock()
        resp.json.return_value = {
            "success": False,
            "errors": [{"code": 9999, "message": "Internal error"}],
        }
        with patch.object(client._session, "request", return_value=resp), pytest.raises(CloudflareError):
            client.disable_email_routing("zone-1")
