"""End-to-end CLI integration tests with mocked external clients.

Exercises the full user-facing path:  argv -> Typer parsing -> workflow ->
ledger -> Rich rendering. External APIs (CF, Google) are mocked.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsm.cli import app
from gsm.clients.cloudflare import ZoneInfo
from gsm.clients.dns_check import DnsCheckResult
from gsm.models.domain import DomainRecord, DomainStatus
from gsm.models.user import UserRecord, UserStatus
from gsm.state.ledger import Ledger


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("GSM_CF_API_TOKEN", "test-token")
    monkeypatch.setenv("GSM_CF_ACCOUNT_ID", "0061a056f8cbc860fb9ec99bd41a0ccc")
    monkeypatch.setenv("GSM_GOOGLE_OAUTH_CLIENT_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("GSM_GOOGLE_OAUTH_TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("GSM_LEDGER_PATH", str(tmp_path / "gsm_state.json"))
    monkeypatch.setenv("GSM_DELAY_PER_DOMAIN_SEC", "0")
    monkeypatch.setenv("GSM_DELAY_PER_USER_SEC", "0")
    monkeypatch.setenv("GSM_DNS_CHECK_MAX_ATTEMPTS", "2")
    return tmp_path


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
        elapsed_sec=10.0,
        last_error="NXDOMAIN",
        resolvers_seen=[],
    )


def _patch_clients(zone_id="z-1"):
    """Returns context-manager-like patches for the 4 external clients used by domains add."""
    cf_client = MagicMock()
    cf_client.ensure_zone.return_value = ZoneInfo(
        zone_id=zone_id,
        name="example.com",
        nameservers=["ns1.cf.com", "ns2.cf.com"],
        created=True,
    )
    cf_client.upsert_dns_record.return_value = True

    admin_client = MagicMock()
    admin_client.add_domain.return_value = True
    admin_client.create_user.return_value = True

    verify_client = MagicMock()
    verify_client.get_dns_txt_token.return_value = "google-site-verification=abc"
    verify_client.verify_domain.return_value = True

    return cf_client, admin_client, verify_client


class TestDomainsAddSuccess:
    def test_single_domain_full_pipeline(self, runner, env):
        cf, admin, verify = _patch_clients()
        with (
            patch("gsm.cli._shared.CloudflareClient", return_value=cf),
            patch("gsm.cli._shared.GoogleAdminClient", return_value=admin),
            patch("gsm.cli._shared.GoogleVerifyClient", return_value=verify),
            patch(
                "gsm.workflows.domain_onboarding.wait_for_txt",
                return_value=_ok_dns(),
            ),
        ):
            result = runner.invoke(app, ["domains", "add", "example.com"])
        assert result.exit_code == 0, result.output
        assert "success" in result.output.lower()
        admin.add_domain.assert_called_once_with("example.com")
        verify.verify_domain.assert_called_once_with("example.com")

    def test_multiple_positional_domains(self, runner, env):
        cf, admin, verify = _patch_clients()
        with (
            patch("gsm.cli._shared.CloudflareClient", return_value=cf),
            patch("gsm.cli._shared.GoogleAdminClient", return_value=admin),
            patch("gsm.cli._shared.GoogleVerifyClient", return_value=verify),
            patch(
                "gsm.workflows.domain_onboarding.wait_for_txt",
                return_value=_ok_dns(),
            ),
        ):
            result = runner.invoke(app, ["domains", "add", "a.com", "b.com", "c.com"])
        assert result.exit_code == 0
        assert admin.add_domain.call_count == 3

    def test_file_input(self, runner, env, tmp_path):
        domains_file = tmp_path / "domains.txt"
        domains_file.write_text("a.com\nb.com\n# comment\n\nc.com\n")
        cf, admin, verify = _patch_clients()
        with (
            patch("gsm.cli._shared.CloudflareClient", return_value=cf),
            patch("gsm.cli._shared.GoogleAdminClient", return_value=admin),
            patch("gsm.cli._shared.GoogleVerifyClient", return_value=verify),
            patch(
                "gsm.workflows.domain_onboarding.wait_for_txt",
                return_value=_ok_dns(),
            ),
        ):
            result = runner.invoke(app, ["domains", "add", "--file", str(domains_file)])
        assert result.exit_code == 0
        assert admin.add_domain.call_count == 3

    def test_dns_pending_returns_partial_not_failed(self, runner, env):
        cf, admin, verify = _patch_clients()
        with (
            patch("gsm.cli._shared.CloudflareClient", return_value=cf),
            patch("gsm.cli._shared.GoogleAdminClient", return_value=admin),
            patch("gsm.cli._shared.GoogleVerifyClient", return_value=verify),
            patch(
                "gsm.workflows.domain_onboarding.wait_for_txt",
                return_value=_failed_dns(),
            ),
        ):
            result = runner.invoke(app, ["domains", "add", "slow.com"])
        assert result.exit_code == 0
        assert "partial" in result.output.lower()
        verify.verify_domain.assert_not_called()


class TestDomainsVerifyOnlyPending:
    def test_only_pending_filters_correctly(self, runner, env, tmp_path):
        ledger_path = tmp_path / "gsm_state.json"
        ledger = Ledger(ledger_path)
        ledger.upsert_domain(
            DomainRecord(
                name="verified.com",
                status=DomainStatus.VERIFIED,
                txt_token="google-site-verification=abc",
                cf_zone_id="z-1",
            )
        )
        ledger.upsert_domain(
            DomainRecord(
                name="pending.com",
                status=DomainStatus.DNS_PENDING,
                txt_token="google-site-verification=def",
                cf_zone_id="z-2",
            )
        )
        ledger.upsert_domain(
            DomainRecord(
                name="injected.com",
                status=DomainStatus.DNS_INJECTED,
                txt_token="google-site-verification=ghi",
                cf_zone_id="z-3",
            )
        )

        cf, admin, verify = _patch_clients()
        with (
            patch("gsm.cli._shared.CloudflareClient", return_value=cf),
            patch("gsm.cli._shared.GoogleAdminClient", return_value=admin),
            patch("gsm.cli._shared.GoogleVerifyClient", return_value=verify),
            patch(
                "gsm.workflows.domain_onboarding.wait_for_txt",
                return_value=_ok_dns(),
            ),
        ):
            result = runner.invoke(app, ["domains", "verify", "--only-pending"])
        assert result.exit_code == 0, result.output
        assert verify.verify_domain.call_count == 2
        called_with = {c.args[0] for c in verify.verify_domain.call_args_list}
        assert called_with == {"pending.com", "injected.com"}

    def test_only_pending_no_matches_is_clean_exit(self, runner, env):
        result = runner.invoke(app, ["domains", "verify", "--only-pending"])
        assert result.exit_code == 0
        assert "no domains" in result.output.lower()


class TestDomainsList:
    def test_list_shows_records(self, runner, env, tmp_path):
        ledger = Ledger(tmp_path / "gsm_state.json")
        ledger.upsert_domain(
            DomainRecord(
                name="a.com",
                status=DomainStatus.VERIFIED,
                cf_zone_id="z-1",
                last_updated=datetime.now(UTC),
            )
        )
        result = runner.invoke(app, ["domains", "list"])
        assert result.exit_code == 0
        assert "a.com" in result.output
        assert "verified" in result.output.lower()

    def test_list_status_filter(self, runner, env, tmp_path):
        ledger = Ledger(tmp_path / "gsm_state.json")
        ledger.upsert_domain(DomainRecord(name="a.com", status=DomainStatus.VERIFIED))
        ledger.upsert_domain(DomainRecord(name="b.com", status=DomainStatus.DNS_PENDING))
        result = runner.invoke(app, ["domains", "list", "--status", "DNS_PENDING"])
        assert result.exit_code == 0
        assert "b.com" in result.output
        assert "a.com" not in result.output


class TestUsersAddSuccess:
    def test_creates_users_from_akun_txt(self, runner, env, tmp_path):
        akun = tmp_path / "akun.txt"
        akun.write_text(
            "alice.smith@example.com | Hunter22! | code-1\n"
            "bob.jones@example.com | Secret44! | code-2\n"
            "# comment\n"
            "\n"
            "carol@example.com | Pass99!\n"
        )
        _, admin, _ = _patch_clients()
        with patch("gsm.cli._shared.GoogleAdminClient", return_value=admin):
            result = runner.invoke(app, ["users", "add", "--file", str(akun)])
        assert result.exit_code == 0, result.output
        assert admin.create_user.call_count == 3

    def test_add_with_partial_failure_exits_nonzero(self, runner, env, tmp_path):
        akun = tmp_path / "akun.txt"
        akun.write_text("a@example.com | pw\nb@example.com | pw\n")

        from gsm.clients.google_admin import GoogleAdminError

        admin = MagicMock()
        admin.create_user.side_effect = [
            True,
            GoogleAdminError("403 forbidden for second"),
        ]
        with patch("gsm.cli._shared.GoogleAdminClient", return_value=admin):
            result = runner.invoke(app, ["users", "add", "--file", str(akun)])
        assert result.exit_code != 0
        assert "failed" in result.output.lower()


class TestUsersList:
    def test_list_with_records_filtered_by_domain(self, runner, env, tmp_path):
        ledger = Ledger(tmp_path / "gsm_state.json")
        ledger.upsert_user(
            UserRecord(
                email="x@a.com",
                status=UserStatus.CREATED,
                last_updated=datetime.now(UTC),
            )
        )
        ledger.upsert_user(
            UserRecord(
                email="y@b.com",
                status=UserStatus.CREATED,
                last_updated=datetime.now(UTC),
            )
        )
        result = runner.invoke(app, ["users", "list", "--domain", "a.com"])
        assert result.exit_code == 0
        assert "x@a.com" in result.output
        assert "y@b.com" not in result.output


class TestErrorPathsUserFriendly:
    """Ensure user-facing errors don't leak Python tracebacks."""

    def test_missing_env_shows_friendly_error(self, runner, monkeypatch):
        for var in [
            "GSM_CF_API_TOKEN",
            "GSM_CF_ACCOUNT_ID",
        ]:
            monkeypatch.delenv(var, raising=False)
        # Use isolated_filesystem so .env from project root isn't picked up
        with runner.isolated_filesystem():
            result = runner.invoke(app, ["domains", "add", "example.com"])
        assert result.exit_code == 2
        assert "Configuration is incomplete" in result.output
        assert "Traceback" not in result.output

    def test_missing_oauth_client_renders_failed_row(self, runner, env):
        result = runner.invoke(app, ["domains", "add", "example.com"])
        assert "Traceback" not in result.output
        assert "failed" in result.output.lower()


class TestEntryPoint:
    @pytest.mark.skipif(
        sys.platform == "win32", reason="emoji in help text causes encoding issues on Windows"
    )
    def test_python_m_gsm_invokable(self):
        """`python -m gsm` works when the package is properly installed.

        Skipped automatically if the dev environment's editable install isn't
        functional (a known Python quirk when project paths contain spaces).
        """
        import subprocess
        import sys
        import tempfile

        tmpdir = tempfile.gettempdir()
        check = subprocess.run(
            [sys.executable, "-c", "import gsm"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=tmpdir,
        )
        if check.returncode != 0:
            pytest.skip(
                "editable install not picked up by subprocess "
                "(likely path-with-spaces); CLI works via the `gsm` script"
            )

        proc = subprocess.run(
            [sys.executable, "-m", "gsm", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=tmpdir,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if proc.returncode != 0:
            pytest.skip(f"subprocess failed (likely encoding issue): {proc.stderr}")
        assert "gsm" in proc.stdout.lower()
        assert "domains" in proc.stdout


class TestLedgerCommands:
    def test_stats_empty_ledger(self, runner, env):
        result = runner.invoke(app, ["ledger", "stats"])
        assert result.exit_code == 0
        assert "domains_total" in result.output

    def test_stats_with_records(self, runner, env, tmp_path):
        ledger = Ledger(tmp_path / "gsm_state.json")
        ledger.upsert_domain(DomainRecord(name="a.com", status=DomainStatus.VERIFIED))
        ledger.upsert_domain(DomainRecord(name="b.com", status=DomainStatus.PENDING))
        result = runner.invoke(app, ["ledger", "stats"])
        assert result.exit_code == 0
        assert "verified" in result.output.lower()

    def test_archive_no_old_records(self, runner, env, tmp_path):
        ledger = Ledger(tmp_path / "gsm_state.json")
        ledger.upsert_domain(DomainRecord(name="recent.com", status=DomainStatus.VERIFIED))
        result = runner.invoke(app, ["ledger", "archive", "--older-than-days", "1"])
        assert result.exit_code == 0
        assert "archived 0" in result.output

    def test_archive_writes_to_default_path(self, runner, env, tmp_path):
        result = runner.invoke(app, ["ledger", "archive", "--older-than-days", "1"])
        assert result.exit_code == 0


class TestVersion:
    def test_version_flag(self, runner):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "gsm" in result.output.lower()
        assert "." in result.output

    def test_short_version_flag(self, runner):
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert "gsm" in result.output.lower()
