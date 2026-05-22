"""Unit tests for workflows/user_bulk_create.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsm.clients.google_admin import GoogleAdminError
from gsm.core.config import Settings
from gsm.models.user import AccountSpec, UserStatus
from gsm.state.ledger import Ledger
from gsm.workflows.user_bulk_create import (
    UserBulkCreator,
    _split_name,
    create_users,
    parse_akun_file,
)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        cf_api_token="t",
        cf_account_id="0061a056f8cbc860fb9ec99bd41a0ccc",
        google_oauth_client_path=tmp_path / "credentials.json",
        google_oauth_token_path=tmp_path / "token.json",
        ledger_path=tmp_path / "gsm_state.json",
        delay_per_user_sec=0.0,
    )


@pytest.fixture
def ledger(settings):
    return Ledger(settings.ledger_path)


@pytest.fixture
def admin():
    a = MagicMock()
    a.create_user.return_value = True
    return a


class TestParseAkun:
    def test_parses_basic_three_field_lines(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text(
            "alice.smith@example.com | hunter2 | code-1\nbob.jones@example.com | secret | code-2\n"
        )
        accounts = parse_akun_file(f)
        assert len(accounts) == 2
        assert accounts[0].email == "alice.smith@example.com"
        assert accounts[0].password.get_secret_value() == "hunter2"
        assert accounts[0].extra_code == "code-1"
        assert accounts[0].first_name == "Alice"
        assert accounts[0].last_name == "Smith"

    def test_skips_blanks_and_comments(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("\n# comment\nuser@example.com | pw\n\n# another comment\n")
        accounts = parse_akun_file(f)
        assert len(accounts) == 1

    def test_skips_lines_without_at_sign(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("valid@example.com | pw\nno-at-sign here\n# also not valid\n")
        accounts = parse_akun_file(f)
        assert len(accounts) == 1
        assert accounts[0].email == "valid@example.com"

    def test_skips_lines_with_too_few_fields(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("alice@example.com\nvalid@example.com | pw\n")
        accounts = parse_akun_file(f)
        assert len(accounts) == 1

    def test_two_field_line_works(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("user@example.com | pw\n")
        accounts = parse_akun_file(f)
        assert accounts[0].extra_code is None

    def test_rejects_malformed_emails(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text(
            "@nolocal | pw\nlocal@ | pw\nlocal@nodot | pw\n  @  | pw\nvalid@example.com | pw\n"
        )
        accounts = parse_akun_file(f)
        assert len(accounts) == 1
        assert accounts[0].email == "valid@example.com"

    def test_rejects_empty_password(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("user@example.com | \nuser2@example.com |   \nvalid@example.com | pw\n")
        accounts = parse_akun_file(f)
        assert len(accounts) == 1
        assert accounts[0].email == "valid@example.com"

    def test_extra_pipe_fields_ignored(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("user@example.com | pw | code | extra | fields\n")
        accounts = parse_akun_file(f)
        assert len(accounts) == 1
        assert accounts[0].password.get_secret_value() == "pw"
        assert accounts[0].extra_code == "code"

    def test_empty_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("")
        assert parse_akun_file(f) == []

    def test_only_comments_returns_empty_list(self, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("# just comments\n# nothing else\n")
        assert parse_akun_file(f) == []

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_akun_file(tmp_path / "nope.txt")


class TestSplitName:
    def test_with_dot(self):
        assert _split_name("alice.smith@x.com") == ("Alice", "Smith")

    def test_without_dot(self):
        assert _split_name("alice@x.com") == ("Alice", "User")

    def test_handles_complex_local_part(self):
        # multiple dots: split on first only
        assert _split_name("a.b.c@x.com") == ("A", "B.c")


class TestUserBulkCreator:
    def test_creates_new_user(self, settings, ledger, admin):
        spec = AccountSpec(
            email="x@example.com",
            password="secret",
            first_name="X",
            last_name="Y",
        )
        creator = UserBulkCreator(settings=settings, ledger=ledger, admin=admin)
        result = creator.run(spec)
        from gsm.models.results import ResultKind

        assert result.kind is ResultKind.SUCCESS
        admin.create_user.assert_called_once()
        record = ledger.get_user("x@example.com")
        assert record is not None
        assert record.status is UserStatus.CREATED

    def test_skips_already_created(self, settings, ledger, admin):
        from datetime import UTC, datetime

        from gsm.models.user import UserRecord

        ledger.upsert_user(
            UserRecord(
                email="dup@example.com",
                status=UserStatus.CREATED,
                last_updated=datetime.now(UTC),
            )
        )
        spec = AccountSpec(
            email="dup@example.com",
            password="x",
            first_name="X",
            last_name="Y",
        )
        creator = UserBulkCreator(settings=settings, ledger=ledger, admin=admin)
        result = creator.run(spec)
        from gsm.models.results import ResultKind

        assert result.kind is ResultKind.SKIPPED
        admin.create_user.assert_not_called()

    def test_admin_failure_records_failed(self, settings, ledger, admin):
        admin.create_user.side_effect = GoogleAdminError("403 forbidden")
        spec = AccountSpec(
            email="bad@example.com",
            password="x",
            first_name="X",
            last_name="Y",
        )
        creator = UserBulkCreator(settings=settings, ledger=ledger, admin=admin)
        result = creator.run(spec)
        from gsm.models.results import ResultKind

        assert result.kind is ResultKind.FAILED
        record = ledger.get_user("bad@example.com")
        assert record is not None
        assert record.status is UserStatus.FAILED
        assert "403 forbidden" in (record.last_error or "")


class TestCreateUsersBatch:
    def test_processes_all_accounts(self, settings, ledger, admin):
        accounts = [
            AccountSpec(
                email=f"u{i}@example.com",
                password="x",
                first_name="X",
                last_name="Y",
            )
            for i in range(3)
        ]
        results = create_users(
            accounts,
            settings=settings,
            ledger=ledger,
            admin=admin,
            delay_per_user_sec=0.0,
        )
        assert len(results) == 3
        assert admin.create_user.call_count == 3
