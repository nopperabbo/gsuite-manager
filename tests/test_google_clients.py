"""Unit tests for clients/google_admin.py and clients/google_verify.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from gsm.clients.google_admin import GoogleAdminClient, GoogleAdminError
from gsm.clients.google_verify import GoogleVerifyClient, GoogleVerifyError


def _http_error(status: int, body: bytes = b"boom"):
    resp = MagicMock()
    resp.status = status
    return HttpError(resp, body)


@pytest.fixture
def auth_admin():
    auth = MagicMock()
    service = MagicMock()
    auth.build_admin_service.return_value = service
    return auth, service


@pytest.fixture
def auth_verify():
    auth = MagicMock()
    service = MagicMock()
    auth.build_verify_service.return_value = service
    return auth, service


class TestGoogleAdminClient:
    def test_add_domain_success(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.return_value = {}

        client = GoogleAdminClient(auth)
        assert client.add_domain("example.com") is True

    def test_add_domain_duplicate_treated_as_success(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = (
            _http_error(409, b'{"error": "Entity already exists"}')
        )
        client = GoogleAdminClient(auth)
        assert client.add_domain("example.com") is True

    def test_add_domain_other_error_raises(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = (
            _http_error(500, b'{"error":"server"}')
        )
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.add_domain("example.com")

    def test_create_user_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.insert.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert (
            client.create_user(
                email="x@example.com",
                password="secret",
                first_name="X",
                last_name="Y",
            )
            is True
        )

    def test_create_user_duplicate_ok(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.insert.return_value.execute.side_effect = (
            _http_error(409, b'{"error":"duplicate"}')
        )
        client = GoogleAdminClient(auth)
        assert (
            client.create_user(
                email="x@example.com",
                password="secret",
                first_name="X",
                last_name="Y",
            )
            is True
        )

    def test_list_domains(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.list.return_value.execute.return_value = {
            "domains": [{"domainName": "a.com"}, {"domainName": "b.com"}]
        }
        client = GoogleAdminClient(auth)
        assert len(client.list_domains()) == 2


class TestGoogleVerifyClient:
    def test_get_token_success(self, auth_verify):
        auth, service = auth_verify
        service.webResource.return_value.getToken.return_value.execute.return_value = {
            "token": "google-site-verification=abc"
        }
        client = GoogleVerifyClient(auth)
        token = client.get_dns_txt_token("example.com")
        assert token == "google-site-verification=abc"

    def test_get_token_empty_response_raises(self, auth_verify):
        auth, service = auth_verify
        service.webResource.return_value.getToken.return_value.execute.return_value = {}
        client = GoogleVerifyClient(auth)
        with pytest.raises(GoogleVerifyError):
            client.get_dns_txt_token("example.com")

    def test_get_token_http_error_raises(self, auth_verify):
        auth, service = auth_verify
        service.webResource.return_value.getToken.return_value.execute.side_effect = (
            _http_error(403)
        )
        client = GoogleVerifyClient(auth)
        with pytest.raises(GoogleVerifyError):
            client.get_dns_txt_token("example.com")

    def test_verify_success(self, auth_verify):
        auth, service = auth_verify
        service.webResource.return_value.insert.return_value.execute.return_value = {
            "id": "site-id"
        }
        client = GoogleVerifyClient(auth)
        assert client.verify_domain("example.com") is True

    def test_verify_already_verified_ok(self, auth_verify):
        auth, service = auth_verify
        service.webResource.return_value.insert.return_value.execute.side_effect = (
            _http_error(400, b'{"error":"already verified"}')
        )
        client = GoogleVerifyClient(auth)
        assert client.verify_domain("example.com") is True

    def test_verify_token_not_found_raises(self, auth_verify):
        auth, service = auth_verify
        service.webResource.return_value.insert.return_value.execute.side_effect = (
            _http_error(
                400,
                b'{"error":"verification token could not be found on your site"}',
            )
        )
        client = GoogleVerifyClient(auth)
        with pytest.raises(GoogleVerifyError):
            client.verify_domain("example.com")
