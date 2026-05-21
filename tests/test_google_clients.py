"""Unit tests for clients/google_admin.py and clients/google_verify.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
    # Disable retry backoff in tests to avoid sleeping
    GoogleAdminClient._retry_backoff = (0.0, 0.0, 0.0)
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


    # --- update_password ---

    def test_update_password_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.update_password(email="u@x.com", password="new") is True

    def test_update_password_http_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = _http_error(404)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.update_password(email="u@x.com", password="new")

    def test_update_password_network_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = OSError("timeout")
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.update_password(email="u@x.com", password="new")

    # --- suspend_user ---

    def test_suspend_user_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.suspend_user("u@x.com") is True

    def test_suspend_user_http_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.suspend_user("u@x.com")

    def test_suspend_user_network_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = TimeoutError()
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.suspend_user("u@x.com")

    # --- unsuspend_user ---

    def test_unsuspend_user_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.unsuspend_user("u@x.com") is True

    def test_unsuspend_user_http_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = _http_error(403)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.unsuspend_user("u@x.com")

    def test_unsuspend_user_network_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = OSError("net")
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.unsuspend_user("u@x.com")

    # --- list_users ---

    def test_list_users_single_page(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.list.return_value.execute.return_value = {
            "users": [{"primaryEmail": "a@x.com"}]
        }
        service.users.return_value.list_next.return_value = None
        client = GoogleAdminClient(auth)
        assert client.list_users() == [{"primaryEmail": "a@x.com"}]

    def test_list_users_multi_page(self, auth_admin):
        auth, service = auth_admin
        page1_req = MagicMock()
        page1_req.execute.return_value = {"users": [{"primaryEmail": "a@x.com"}]}
        page2_req = MagicMock()
        page2_req.execute.return_value = {"users": [{"primaryEmail": "b@x.com"}]}
        service.users.return_value.list.return_value = page1_req
        service.users.return_value.list_next.side_effect = [page2_req, None]
        client = GoogleAdminClient(auth)
        result = client.list_users()
        assert len(result) == 2

    def test_list_users_empty(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.list.return_value.execute.return_value = {}
        service.users.return_value.list_next.return_value = None
        client = GoogleAdminClient(auth)
        assert client.list_users() == []

    def test_list_users_http_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.list.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.list_users()

    # --- move_user_to_ou ---

    def test_move_user_to_ou_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.move_user_to_ou("u@x.com", "/Sales") is True

    def test_move_user_to_ou_http_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = _http_error(404)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.move_user_to_ou("u@x.com", "/Sales")

    # --- delete_user ---

    def test_delete_user_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.delete.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.delete_user("u@x.com") is True

    def test_delete_user_not_found_ok(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.delete.return_value.execute.side_effect = (
            _http_error(404, b'{"error":"resource not found"}')
        )
        client = GoogleAdminClient(auth)
        assert client.delete_user("u@x.com") is True

    def test_delete_user_other_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.delete.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.delete_user("u@x.com")

    def test_delete_user_network_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.delete.return_value.execute.side_effect = OSError("net")
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.delete_user("u@x.com")

    # --- add_alias ---

    def test_add_alias_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.insert.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.add_alias("u@x.com", "a@x.com") is True

    def test_add_alias_duplicate_ok(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.insert.return_value.execute.side_effect = (
            _http_error(409, b'{"error":"duplicate"}')
        )
        client = GoogleAdminClient(auth)
        assert client.add_alias("u@x.com", "a@x.com") is True

    def test_add_alias_other_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.insert.return_value.execute.side_effect = (
            _http_error(500)
        )
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.add_alias("u@x.com", "a@x.com")

    # --- list_aliases ---

    def test_list_aliases_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.list.return_value.execute.return_value = {
            "aliases": [{"alias": "a@x.com"}, {"alias": "b@x.com"}]
        }
        client = GoogleAdminClient(auth)
        assert client.list_aliases("u@x.com") == ["a@x.com", "b@x.com"]

    def test_list_aliases_empty(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.list.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.list_aliases("u@x.com") == []

    def test_list_aliases_http_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.list.return_value.execute.side_effect = (
            _http_error(500)
        )
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.list_aliases("u@x.com")

    # --- remove_alias ---

    def test_remove_alias_success(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.delete.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.remove_alias("u@x.com", "a@x.com") is True

    def test_remove_alias_not_found_ok(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.delete.return_value.execute.side_effect = (
            _http_error(404, b'{"error":"not found"}')
        )
        client = GoogleAdminClient(auth)
        assert client.remove_alias("u@x.com", "a@x.com") is True

    def test_remove_alias_other_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.aliases.return_value.delete.return_value.execute.side_effect = (
            _http_error(500)
        )
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.remove_alias("u@x.com", "a@x.com")

    # --- assign_license ---

    def test_assign_license_success(self, auth_admin):
        auth, _service = auth_admin
        auth.get_credentials.return_value = MagicMock()
        mock_licensing = MagicMock()
        mock_licensing.licenseAssignments.return_value.insert.return_value.execute.return_value = {}
        with patch("googleapiclient.discovery.build", return_value=mock_licensing):
            client = GoogleAdminClient(auth)
            assert client.assign_license("u@x.com", "sku1", "prod1") is True

    def test_assign_license_duplicate_ok(self, auth_admin):
        auth, _service = auth_admin
        auth.get_credentials.return_value = MagicMock()
        mock_licensing = MagicMock()
        mock_licensing.licenseAssignments.return_value.insert.return_value.execute.side_effect = (
            _http_error(409, b'{"error":"duplicate"}')
        )
        with patch("googleapiclient.discovery.build", return_value=mock_licensing):
            client = GoogleAdminClient(auth)
            assert client.assign_license("u@x.com", "sku1", "prod1") is True

    def test_assign_license_http_error(self, auth_admin):
        auth, _service = auth_admin
        auth.get_credentials.return_value = MagicMock()
        mock_licensing = MagicMock()
        mock_licensing.licenseAssignments.return_value.insert.return_value.execute.side_effect = (
            _http_error(500)
        )
        with patch("googleapiclient.discovery.build", return_value=mock_licensing):
            client = GoogleAdminClient(auth)
            with pytest.raises(GoogleAdminError):
                client.assign_license("u@x.com", "sku1", "prod1")

    # --- create_group ---

    def test_create_group_success(self, auth_admin):
        auth, service = auth_admin
        service.groups.return_value.insert.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.create_group("g@x.com", name="Group") is True

    def test_create_group_duplicate_ok(self, auth_admin):
        auth, service = auth_admin
        service.groups.return_value.insert.return_value.execute.side_effect = (
            _http_error(409, b'{"error":"Entity already exists"}')
        )
        client = GoogleAdminClient(auth)
        assert client.create_group("g@x.com") is True

    def test_create_group_http_error(self, auth_admin):
        auth, service = auth_admin
        service.groups.return_value.insert.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.create_group("g@x.com")

    # --- list_groups ---

    def test_list_groups_paginated(self, auth_admin):
        auth, service = auth_admin
        page1_req = MagicMock()
        page1_req.execute.return_value = {"groups": [{"email": "g1@x.com"}]}
        page2_req = MagicMock()
        page2_req.execute.return_value = {"groups": [{"email": "g2@x.com"}]}
        service.groups.return_value.list.return_value = page1_req
        service.groups.return_value.list_next.side_effect = [page2_req, None]
        client = GoogleAdminClient(auth)
        assert len(client.list_groups()) == 2

    def test_list_groups_http_error(self, auth_admin):
        auth, service = auth_admin
        service.groups.return_value.list.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.list_groups()

    # --- add_group_member ---

    def test_add_group_member_success(self, auth_admin):
        auth, service = auth_admin
        service.members.return_value.insert.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.add_group_member("g@x.com", "u@x.com") is True

    def test_add_group_member_duplicate_ok(self, auth_admin):
        auth, service = auth_admin
        service.members.return_value.insert.return_value.execute.side_effect = (
            _http_error(409, b'{"error":"Entity already exists"}')
        )
        client = GoogleAdminClient(auth)
        assert client.add_group_member("g@x.com", "u@x.com") is True

    def test_add_group_member_http_error(self, auth_admin):
        auth, service = auth_admin
        service.members.return_value.insert.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.add_group_member("g@x.com", "u@x.com")

    # --- remove_group_member ---

    def test_remove_group_member_success(self, auth_admin):
        auth, service = auth_admin
        service.members.return_value.delete.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.remove_group_member("g@x.com", "u@x.com") is True

    def test_remove_group_member_not_found_ok(self, auth_admin):
        auth, service = auth_admin
        service.members.return_value.delete.return_value.execute.side_effect = (
            _http_error(404, b'{"error":"resource not found"}')
        )
        client = GoogleAdminClient(auth)
        assert client.remove_group_member("g@x.com", "u@x.com") is True

    def test_remove_group_member_http_error(self, auth_admin):
        auth, service = auth_admin
        service.members.return_value.delete.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.remove_group_member("g@x.com", "u@x.com")

    # --- list_group_members ---

    def test_list_group_members_paginated(self, auth_admin):
        auth, service = auth_admin
        page1_req = MagicMock()
        page1_req.execute.return_value = {"members": [{"email": "u1@x.com"}]}
        page2_req = MagicMock()
        page2_req.execute.return_value = {"members": [{"email": "u2@x.com"}]}
        service.members.return_value.list.return_value = page1_req
        service.members.return_value.list_next.side_effect = [page2_req, None]
        client = GoogleAdminClient(auth)
        assert len(client.list_group_members("g@x.com")) == 2

    def test_list_group_members_http_error(self, auth_admin):
        auth, service = auth_admin
        service.members.return_value.list.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.list_group_members("g@x.com")

    # --- update_user ---

    def test_update_user_name_fields(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.update_user("u@x.com", first_name="A", last_name="B") is True

    def test_update_user_department_title(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.update_user("u@x.com", department="Eng", title="SWE") is True

    def test_update_user_phone(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.return_value = {}
        client = GoogleAdminClient(auth)
        assert client.update_user("u@x.com", phone="+1234") is True

    def test_update_user_empty_returns_false(self, auth_admin):
        auth, _service = auth_admin
        client = GoogleAdminClient(auth)
        assert client.update_user("u@x.com") is False

    def test_update_user_http_error(self, auth_admin):
        auth, service = auth_admin
        service.users.return_value.update.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.update_user("u@x.com", first_name="A")


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


class TestGoogleAdminRetry:
    """Tests for the _exec retry logic in GoogleAdminClient."""

    def test_retries_on_500_then_succeeds(self, auth_admin):
        auth, service = auth_admin
        # First call raises 500, second succeeds
        service.domains.return_value.insert.return_value.execute.side_effect = [
            _http_error(500),
            {},
        ]
        client = GoogleAdminClient(auth)
        assert client.add_domain("retry.com") is True

    def test_retries_on_429_then_succeeds(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = [
            _http_error(429),
            {},
        ]
        client = GoogleAdminClient(auth)
        assert client.add_domain("ratelimit.com") is True

    def test_retries_on_503_then_succeeds(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = [
            _http_error(503),
            _http_error(502),
            {},
        ]
        client = GoogleAdminClient(auth)
        assert client.add_domain("flaky.com") is True

    def test_no_retry_on_403(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = _http_error(403)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.add_domain("forbidden.com")
        # Should only be called once (no retry)
        assert service.domains.return_value.insert.return_value.execute.call_count == 1

    def test_exhausts_retries_on_persistent_500(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = _http_error(500)
        client = GoogleAdminClient(auth)
        with pytest.raises(GoogleAdminError):
            client.add_domain("down.com")
        # Should be called 3 times (initial + 2 retries)
        assert service.domains.return_value.insert.return_value.execute.call_count == 3

    def test_retries_on_timeout_then_succeeds(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = [
            TimeoutError("timed out"),
            {},
        ]
        client = GoogleAdminClient(auth)
        assert client.add_domain("slow.com") is True

    def test_retries_on_oserror_then_succeeds(self, auth_admin):
        auth, service = auth_admin
        service.domains.return_value.insert.return_value.execute.side_effect = [
            OSError("connection reset"),
            {},
        ]
        client = GoogleAdminClient(auth)
        assert client.add_domain("unstable.com") is True
