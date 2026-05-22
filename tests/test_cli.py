"""CLI tests using typer's CliRunner. Covers init + doctor + smoke list commands."""

from __future__ import annotations

import stat
import sys
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsm.cli import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def env_for_cli(monkeypatch, tmp_path):
    """Set up minimum env vars required for Settings to load in CLI commands."""
    monkeypatch.setenv("GSM_CF_API_TOKEN", "dummy-token")
    monkeypatch.setenv("GSM_CF_ACCOUNT_ID", "0061a056f8cbc860fb9ec99bd41a0ccc")
    monkeypatch.setenv(
        "GSM_GOOGLE_OAUTH_CLIENT_PATH",
        str(tmp_path / "credentials.json"),
    )
    monkeypatch.setenv("GSM_GOOGLE_OAUTH_TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("GSM_LEDGER_PATH", str(tmp_path / "gsm_state.json"))
    monkeypatch.setenv("GSM_DELAY_PER_DOMAIN_SEC", "0")
    monkeypatch.setenv("GSM_DELAY_PER_USER_SEC", "0")
    return tmp_path


def test_root_help(runner):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "domains" in result.stdout
    assert "users" in result.stdout
    assert "init" in result.stdout
    assert "doctor" in result.stdout


def test_domains_help(runner):
    result = runner.invoke(app, ["domains", "--help"])
    assert result.exit_code == 0
    assert "add" in result.stdout
    assert "verify" in result.stdout


def test_users_help(runner):
    result = runner.invoke(app, ["users", "--help"])
    assert result.exit_code == 0
    assert "add" in result.stdout


class TestInit:
    def test_init_writes_env_template(self, runner, tmp_path):
        result = runner.invoke(app, ["init", "--cwd", str(tmp_path)])
        assert result.exit_code == 0
        env_file = tmp_path / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert "GSM_CF_API_TOKEN" in content
        assert "GSM_DNS_CHECK_RESOLVERS" in content

    def test_init_refuses_to_overwrite_without_force(self, runner, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING=1")
        result = runner.invoke(app, ["init", "--cwd", str(tmp_path)])
        assert result.exit_code == 0
        assert env_file.read_text() == "EXISTING=1"

    def test_init_with_force_overwrites(self, runner, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING=1")
        result = runner.invoke(app, ["init", "--cwd", str(tmp_path), "--force"])
        assert result.exit_code == 0
        assert "GSM_CF_API_TOKEN" in env_file.read_text()


class TestDoctor:
    def test_doctor_passes_when_everything_ok(self, runner, env_for_cli, tmp_path):
        (tmp_path / "credentials.json").write_text("{}")

        cf_resp = MagicMock()
        cf_resp.json.return_value = {
            "success": True,
            "result": {"status": "active"},
        }

        with (
            patch("gsm.cli.commands.doctor.requests.get", return_value=cf_resp),
            patch("gsm.cli.commands.doctor.dns.resolver.Resolver") as resolver_cls,
        ):
            instance = MagicMock()
            instance.resolve.return_value = MagicMock()
            resolver_cls.return_value = instance
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0, result.stdout
        assert "PASS" in result.stdout

    def test_doctor_reports_invalid_cf_token(self, runner, env_for_cli, tmp_path):
        (tmp_path / "credentials.json").write_text("{}")
        cf_resp = MagicMock()
        cf_resp.json.return_value = {
            "success": False,
            "errors": [{"message": "invalid token"}],
        }
        with (
            patch("gsm.cli.commands.doctor.requests.get", return_value=cf_resp),
            patch("gsm.cli.commands.doctor.dns.resolver.Resolver") as resolver_cls,
        ):
            instance = MagicMock()
            instance.resolve.return_value = MagicMock()
            resolver_cls.return_value = instance
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "FAIL" in result.stdout


class TestDomainsList:
    def test_list_empty_ledger(self, runner, env_for_cli):
        result = runner.invoke(app, ["domains", "list"])
        assert result.exit_code == 0
        assert "no domains in ledger" in result.stdout

    def test_list_invalid_status_rejected(self, runner, env_for_cli):
        result = runner.invoke(app, ["domains", "list", "--status", "BOGUS"])
        assert result.exit_code != 0
        assert "unknown status" in result.output


class TestUsersList:
    def test_list_empty(self, runner, env_for_cli):
        result = runner.invoke(app, ["users", "list"])
        assert result.exit_code == 0
        assert "no users in ledger" in result.stdout

    def test_list_invalid_status_rejected(self, runner, env_for_cli):
        result = runner.invoke(app, ["users", "list", "--status", "BOGUS"])
        assert result.exit_code != 0


class TestUsersAddInputErrors:
    def test_missing_file_fails_gracefully(self, runner, env_for_cli):
        result = runner.invoke(app, ["users", "add", "--file", "/no/such/path.txt"])
        assert result.exit_code != 0


class TestDomainsAddInputErrors:
    def test_no_input_rejected(self, runner, env_for_cli):
        result = runner.invoke(app, ["domains", "add"])
        assert result.exit_code != 0
        assert "provide" in result.output.lower()

    def test_file_not_found(self, runner, env_for_cli):
        result = runner.invoke(app, ["domains", "add", "--file", "/no/such/file.txt"])
        assert result.exit_code != 0


class TestUsersGen:
    """Tests for `gsm users gen` (auto username generator)."""

    def test_help(self, runner):
        result = runner.invoke(app, ["users", "gen", "--help"])
        assert result.exit_code == 0
        assert "--domain" in result.stdout
        assert "--count" in result.stdout
        assert "--locale" in result.stdout
        assert "--pattern" in result.stdout

    def test_preview_only_redacts_password(self, runner, env_for_cli):
        """Without --output or --apply, password should be redacted."""
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "bunhe.tech",
                "--count",
                "3",
                "--seed",
                "42",
            ],
        )
        assert result.exit_code == 0, result.stdout
        # Password should be redacted in preview-only mode
        assert "******" in result.stdout
        # But emails should be visible
        assert "@bunhe.tech" in result.stdout
        # Should hint at next step
        assert "--output" in result.stdout or "--apply" in result.stdout

    def test_output_writes_akun_file(self, runner, env_for_cli, tmp_path):
        out_file = tmp_path / "generated.txt"
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "bunhe.tech",
                "--count",
                "5",
                "--seed",
                "1",
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert out_file.exists()
        lines = out_file.read_text().strip().splitlines()
        assert len(lines) == 5
        for line in lines:
            parts = line.split("|")
            assert len(parts) == 3, f"expected 3 parts, got {parts}"
            assert "@bunhe.tech" in parts[0]
            assert parts[1]  # password non-empty
            # extra_code may be empty (parts[2] == "")

    def test_output_file_compatible_with_users_add(self, runner, env_for_cli, tmp_path):
        """Output file format must round-trip via parse_akun_file."""
        from gsm.workflows.user_bulk_create import parse_akun_file

        out_file = tmp_path / "generated.txt"
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "bunhe.tech",
                "--count",
                "4",
                "--seed",
                "7",
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0, result.stdout

        accounts = parse_akun_file(out_file)
        assert len(accounts) == 4
        for acc in accounts:
            assert acc.email.endswith("@bunhe.tech")
            assert acc.password.get_secret_value()
            assert acc.first_name
            assert acc.last_name

    def test_output_file_perms_0600(self, runner, env_for_cli, tmp_path):
        """Generated file should be mode 0600 (POSIX) for password safety."""
        import os

        if os.name != "posix":
            pytest.skip("chmod is no-op on Windows")

        out_file = tmp_path / "generated.txt"
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "bunhe.tech",
                "--count",
                "1",
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0
        if sys.platform != "win32":
            mode = stat.S_IMODE(out_file.stat().st_mode)
            assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    def test_invalid_pattern_rejected(self, runner, env_for_cli):
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "bunhe.tech",
                "--count",
                "3",
                "--pattern",
                "noatsign{first}.{domain}",
            ],
        )
        assert result.exit_code == 2
        assert "Generator error" in result.output or "harus" in result.output

    def test_count_zero_rejected_by_typer(self, runner, env_for_cli):
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "bunhe.tech",
                "--count",
                "0",
            ],
        )
        # typer's `min=1` should reject this before reaching our code
        assert result.exit_code != 0

    def test_collision_aware_with_ledger(self, runner, env_for_cli, tmp_path):
        """If ledger has existing users for the domain, generator should skip them."""
        # Pre-populate ledger via direct write (cheaper than using `gsm users add`)
        from datetime import UTC, datetime

        ledger_path = tmp_path / "gsm_state.json"
        existing_email = "andi.saputra@bunhe.tech"
        ledger_data = {
            "version": 1,
            "domains": {},
            "users": {
                existing_email: {
                    "email": existing_email,
                    "status": "created",
                    "first_name": "Andi",
                    "last_name": "Saputra",
                    "first_seen": datetime.now(UTC).isoformat(),
                    "last_updated": datetime.now(UTC).isoformat(),
                    "last_error": None,
                }
            },
        }
        import json

        ledger_path.write_text(json.dumps(ledger_data))

        out_file = tmp_path / "generated.txt"
        # Use a pattern that would deterministically produce
        # andi.saputra@bunhe.tech if Faker picks Andi/Saputra; we can't
        # force that here, but we CAN check the "skip N existing" message
        # appears.
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "bunhe.tech",
                "--count",
                "2",
                "--seed",
                "5",
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "Skip 1" in result.output  # 1 existing user
        # And the existing email must NOT appear in the output file
        emails_in_file = [line.split("|")[0] for line in out_file.read_text().strip().splitlines()]
        assert existing_email not in emails_in_file

    def test_locale_en_us(self, runner, env_for_cli):
        result = runner.invoke(
            app,
            [
                "users",
                "gen",
                "--domain",
                "x.com",
                "--count",
                "3",
                "--locale",
                "en_US",
                "--seed",
                "1",
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "@x.com" in result.stdout


class TestDomainsCheckMx:
    """Tests for `gsm domains check-mx` (Gmail readiness check)."""

    def test_help(self, runner):
        result = runner.invoke(app, ["domains", "check-mx", "--help"])
        assert result.exit_code == 0
        assert "MX" in result.stdout or "mx" in result.stdout

    def test_healthy_domain_exit_code_0(self, runner, env_for_cli):
        from gsm.clients.mx_check import EXPECTED_GOOGLE_MX

        def _mk(host, prio):
            r = MagicMock()
            r.exchange = MagicMock()
            r.exchange.__str__ = MagicMock(return_value=f"{host}.")
            r.preference = prio
            return r

        records = [_mk(host, prio) for host, prio in EXPECTED_GOOGLE_MX]

        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = runner.invoke(app, ["domains", "check-mx", "bunhe.tech"])
        assert result.exit_code == 0, result.stdout
        assert "healthy" in result.stdout.lower()

    def test_not_google_domain_exits_nonzero(self, runner, env_for_cli):
        def _mk(host, prio):
            r = MagicMock()
            r.exchange = MagicMock()
            r.exchange.__str__ = MagicMock(return_value=f"{host}.")
            r.preference = prio
            return r

        records = [_mk("smtp.outlook.com", 10)]

        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = runner.invoke(app, ["domains", "check-mx", "bunhe.tech"])
        assert result.exit_code == 1
        assert "not_google" in result.stdout.lower() or "Outlook" in result.output

    def test_no_input_rejected(self, runner, env_for_cli):
        result = runner.invoke(app, ["domains", "check-mx"])
        assert result.exit_code != 0

    def test_all_flag_with_empty_ledger(self, runner, env_for_cli):
        result = runner.invoke(app, ["domains", "check-mx", "--all"])
        assert result.exit_code == 0
        assert "Tidak ada domain VERIFIED" in result.output

    def test_json_output(self, runner, env_for_cli):
        from gsm.clients.mx_check import EXPECTED_GOOGLE_MX

        def _mk(host, prio):
            r = MagicMock()
            r.exchange = MagicMock()
            r.exchange.__str__ = MagicMock(return_value=f"{host}.")
            r.preference = prio
            return r

        records = [_mk(host, prio) for host, prio in EXPECTED_GOOGLE_MX]

        with patch("dns.resolver.Resolver") as resolver_cls:
            instance = MagicMock()
            instance.resolve.return_value = records
            resolver_cls.return_value = instance
            result = runner.invoke(app, ["domains", "check-mx", "bunhe.tech", "--json"])
        assert result.exit_code == 0, result.stdout
        import json

        payload = json.loads(result.stdout)
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["domain"] == "bunhe.tech"
        assert payload[0]["status"] == "healthy"
        assert payload[0]["is_healthy"] is True


class TestDomainsImport:
    """Tests for `gsm domains import` (Cloudflare zone import)."""

    def test_help(self, runner):
        result = runner.invoke(app, ["domains", "import", "--help"])
        assert result.exit_code == 0
        assert "--from" in result.stdout
        assert "--filter" in result.stdout
        assert "--all" in result.stdout
        assert "--dry-run" in result.stdout

    def test_unsupported_source_rejected(self, runner, env_for_cli):
        result = runner.invoke(app, ["domains", "import", "--from", "namecheap"])
        assert result.exit_code == 2
        assert "tidak didukung" in result.output

    def test_empty_cf_account_returns_zero(self, runner, env_for_cli):
        with patch("gsm.cli._shared.CloudflareClient") as cf_cls:
            cf_instance = MagicMock()
            cf_instance.list_zones.return_value = []
            cf_cls.return_value = cf_instance
            result = runner.invoke(app, ["domains", "import"])
        assert result.exit_code == 0
        assert "Tidak ada zone" in result.output

    def test_dry_run_no_onboarding(self, runner, env_for_cli):
        from gsm.clients.cloudflare import ZoneInfo

        zones = [
            ZoneInfo(
                zone_id="z1",
                name="foo.tech",
                nameservers=["ns1.cloudflare.com"],
                created=False,
            ),
            ZoneInfo(
                zone_id="z2",
                name="bar.com",
                nameservers=["ns1.cloudflare.com"],
                created=False,
            ),
        ]
        with patch("gsm.cli._shared.CloudflareClient") as cf_cls:
            cf_instance = MagicMock()
            cf_instance.list_zones.return_value = zones
            cf_cls.return_value = cf_instance
            result = runner.invoke(app, ["domains", "import", "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower()
        assert "2 zone" in result.output

    def test_filter_glob_excludes_non_matching(self, runner, env_for_cli):
        from gsm.clients.cloudflare import ZoneInfo

        zones = [
            ZoneInfo(
                zone_id="z1",
                name="foo.tech",
                nameservers=[],
                created=False,
            ),
            ZoneInfo(
                zone_id="z2",
                name="bar.com",
                nameservers=[],
                created=False,
            ),
        ]
        with patch("gsm.cli._shared.CloudflareClient") as cf_cls:
            cf_instance = MagicMock()
            cf_instance.list_zones.return_value = zones
            cf_cls.return_value = cf_instance
            result = runner.invoke(
                app,
                [
                    "domains",
                    "import",
                    "--filter",
                    "*.tech",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert "1 zone" in result.output  # only foo.tech matched

    def test_output_writes_domain_list(self, runner, env_for_cli, tmp_path):
        from gsm.clients.cloudflare import ZoneInfo

        zones = [
            ZoneInfo(
                zone_id="z1",
                name="foo.tech",
                nameservers=[],
                created=False,
            ),
            ZoneInfo(
                zone_id="z2",
                name="bar.com",
                nameservers=[],
                created=False,
            ),
        ]
        out = tmp_path / "imported.txt"
        with patch("gsm.cli._shared.CloudflareClient") as cf_cls:
            cf_instance = MagicMock()
            cf_instance.list_zones.return_value = zones
            cf_cls.return_value = cf_instance
            result = runner.invoke(
                app,
                [
                    "domains",
                    "import",
                    "--all",
                    "--output",
                    str(out),
                ],
            )
        assert result.exit_code == 0, result.stdout
        assert out.exists()
        lines = out.read_text().strip().splitlines()
        assert sorted(lines) == ["bar.com", "foo.tech"]

    def test_all_verified_zones_skipped(self, runner, env_for_cli, tmp_path):
        """If every zone in CF is already VERIFIED in ledger, command exits clean."""
        from datetime import UTC, datetime

        from gsm.clients.cloudflare import ZoneInfo

        ledger_path = tmp_path / "gsm_state.json"
        now = datetime.now(UTC).isoformat()
        ledger_data = {
            "version": 1,
            "domains": {
                "foo.tech": {
                    "name": "foo.tech",
                    "status": "verified",
                    "first_seen": now,
                    "last_updated": now,
                },
            },
            "users": {},
        }
        import json

        ledger_path.write_text(json.dumps(ledger_data))

        zones = [
            ZoneInfo(
                zone_id="z1",
                name="foo.tech",
                nameservers=[],
                created=False,
            ),
        ]
        with patch("gsm.cli._shared.CloudflareClient") as cf_cls:
            cf_instance = MagicMock()
            cf_instance.list_zones.return_value = zones
            cf_cls.return_value = cf_instance
            result = runner.invoke(app, ["domains", "import"])
        assert result.exit_code == 0
        assert "VERIFIED" in result.output
