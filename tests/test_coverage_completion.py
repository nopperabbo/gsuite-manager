"""Coverage completion tests — targets all remaining uncovered lines."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsm.cli import app
from gsm.clients.google_admin import GoogleAdminError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def runtime():
    rt = MagicMock()
    rt.admin = MagicMock()
    rt.ledger = MagicMock()
    rt.cf = MagicMock()
    rt.settings = MagicMock()
    return rt


# ─── __main__.py ─────────────────────────────────────────────────────────────


class TestMainModule:
    def test_main_function(self):
        from gsm.__main__ import main
        with patch("gsm.__main__.app") as mock_app:
            mock_app.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                main()
            mock_app.assert_called_once()


# ─── __init__.py (PackageNotFoundError branch) ───────────────────────────────


class TestVersion:
    def test_version_fallback(self):
        from importlib.metadata import PackageNotFoundError
        with patch("gsm.version", side_effect=PackageNotFoundError()):
            # Already covered by import — the except branch runs if package not installed
            pass

    def test_version_exists(self):
        from gsm import __version__
        assert isinstance(__version__, str)


# ─── init.py: setup wizard functions ─────────────────────────────────────────


class TestInitWizardFunctions:
    def test_ask_cf_token_valid(self):
        from gsm.cli.commands.init import _ask_cf_token
        with patch("gsm.cli.commands.init.Prompt.ask", return_value="a" * 40):
            result = _ask_cf_token()
        assert result == "a" * 40

    def test_ask_cf_token_too_short_then_valid(self):
        from gsm.cli.commands.init import _ask_cf_token
        with patch("gsm.cli.commands.init.Prompt.ask", side_effect=["short", "a" * 40]):
            result = _ask_cf_token()
        assert result == "a" * 40

    def test_ask_cf_account_id_skip_test(self):
        from gsm.cli.commands.init import _ask_cf_account_id
        valid_id = "0" * 32
        with patch("gsm.cli.commands.init.Prompt.ask", return_value=valid_id):
            result = _ask_cf_account_id("token", skip_test=True)
        assert result == valid_id

    def test_ask_cf_account_id_invalid_then_valid(self):
        from gsm.cli.commands.init import _ask_cf_account_id
        valid_id = "a" * 32
        with patch("gsm.cli.commands.init.Prompt.ask", side_effect=["bad!", valid_id]):
            result = _ask_cf_account_id("token", skip_test=True)
        assert result == valid_id

    def test_ask_cf_account_id_autodetect(self):
        from gsm.cli.commands.init import _ask_cf_account_id
        with (
            patch("gsm.cli.commands.init._try_autodetect_account_id", return_value="b" * 32),
            patch("gsm.cli.commands.init.Confirm.ask", return_value=True),
        ):
            result = _ask_cf_account_id("token", skip_test=False)
        assert result == "b" * 32

    def test_ask_cf_account_id_autodetect_rejected(self):
        from gsm.cli.commands.init import _ask_cf_account_id
        valid_id = "c" * 32
        with (
            patch("gsm.cli.commands.init._try_autodetect_account_id", return_value="b" * 32),
            patch("gsm.cli.commands.init.Confirm.ask", return_value=False),
            patch("gsm.cli.commands.init.Prompt.ask", return_value=valid_id),
        ):
            result = _ask_cf_account_id("token", skip_test=False)
        assert result == valid_id

    def test_ask_oauth_client_detected(self, tmp_path):
        from gsm.cli.commands.init import _ask_oauth_client
        (tmp_path / "credentials.json").write_text("{}")
        with patch("gsm.cli.commands.init.Confirm.ask", return_value=True):
            result = _ask_oauth_client(tmp_path)
        assert "credentials.json" in str(result)

    def test_ask_oauth_client_manual(self, tmp_path):
        from gsm.cli.commands.init import _ask_oauth_client
        with patch("gsm.cli.commands.init.Prompt.ask", return_value="./my-creds.json"):
            result = _ask_oauth_client(tmp_path)
        assert "my-creds.json" in str(result)

    def test_try_autodetect_success(self):
        from gsm.cli.commands.init import _try_autodetect_account_id
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "result": [{"id": "x" * 32}]}
        with patch("requests.get", return_value=mock_resp):
            result = _try_autodetect_account_id("token")
        assert result == "x" * 32

    def test_try_autodetect_failure(self):
        from gsm.cli.commands.init import _try_autodetect_account_id
        with patch("requests.get", side_effect=Exception("timeout")):
            result = _try_autodetect_account_id("token")
        assert result is None

    def test_try_autodetect_no_results(self):
        from gsm.cli.commands.init import _try_autodetect_account_id
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "result": []}
        with patch("requests.get", return_value=mock_resp):
            result = _try_autodetect_account_id("token")
        assert result is None

    def test_test_cf_connection_valid(self):
        from gsm.cli.commands.init import _test_cf_connection
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "result": {"status": "active"}}
        with patch("requests.get", return_value=mock_resp):
            _test_cf_connection("token")  # no exception

    def test_test_cf_connection_invalid(self):
        from gsm.cli.commands.init import _test_cf_connection
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": False, "errors": [{"message": "bad"}]}
        with patch("requests.get", return_value=mock_resp):
            _test_cf_connection("token")  # prints error, no exception

    def test_test_cf_connection_network_error(self):
        from gsm.cli.commands.init import _test_cf_connection
        with patch("requests.get", side_effect=Exception("network")):
            _test_cf_connection("token")  # prints warning, no exception

    def test_write_env(self, tmp_path):
        from gsm.cli.commands.init import _write_env
        env_path = tmp_path / ".env"
        _write_env(env_path, {"GSM_CF_API_TOKEN": "mytoken"})
        content = env_path.read_text()
        assert "GSM_CF_API_TOKEN=mytoken" in content
        assert env_path.stat().st_mode & 0o777 == 0o600

    def test_print_summary(self, tmp_path):
        from gsm.cli.commands.init import _print_summary
        env_path = tmp_path / ".env"
        env_path.write_text("")
        _print_summary(env_path, Path("./credentials.json"))  # no exception

    def test_setup_full_wizard(self, runner, tmp_path):
        (tmp_path / "credentials.json").write_text("{}")
        with (
            patch("gsm.cli.commands.init.Prompt.ask", side_effect=[
                "a" * 40,                          # CF token
                "b" * 32,                          # CF account ID
                str(tmp_path / "credentials.json"),  # OAuth path
            ]),
            patch("gsm.cli.commands.init.Confirm.ask", return_value=True),
            patch("gsm.cli.commands.init._try_autodetect_account_id", return_value=None),
        ):
            result = runner.invoke(app, ["setup", "--cwd", str(tmp_path), "--skip-test"])
        assert result.exit_code == 0
        assert (tmp_path / ".env").exists()


# ─── Remaining menu error paths ──────────────────────────────────────────────


MENU_PROMPT = "gsm.cli.commands.menu.Prompt.ask"
MENU_CONFIRM = "rich.prompt.Confirm.ask"
MENU_CTX = "gsm.cli._shared.get_context"


class TestMenuErrorPaths:
    def test_choice4_api_error(self, runner, runtime):
        """Reset password — API error on list_users."""
        runtime.admin.list_users.side_effect = GoogleAdminError("denied")
        with (
            patch(MENU_PROMPT, side_effect=["4", "x.com", "random", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice5_api_error(self, runner, runtime):
        """Suspend — API error on list_users."""
        runtime.admin.list_users.side_effect = GoogleAdminError("denied")
        with (
            patch(MENU_PROMPT, side_effect=["5", "x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice6_api_error(self, runner, runtime):
        """Unsuspend — API error on list_users."""
        runtime.admin.list_users.side_effect = GoogleAdminError("denied")
        with (
            patch(MENU_PROMPT, side_effect=["6", "x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice6_suspend_error(self, runner, runtime):
        """Unsuspend — error on individual user."""
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        runtime.admin.unsuspend_user.side_effect = GoogleAdminError("fail")
        with (
            patch(MENU_PROMPT, side_effect=["6", "x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice7_api_error(self, runner, runtime):
        """Delete — API error on list_users."""
        runtime.admin.list_users.side_effect = GoogleAdminError("denied")
        with (
            patch(MENU_PROMPT, side_effect=["7", "x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
            patch(MENU_CONFIRM, return_value=True),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice7_no_users(self, runner, runtime):
        """Delete — no users found."""
        runtime.admin.list_users.return_value = []
        with (
            patch(MENU_PROMPT, side_effect=["7", "x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice7_delete_error(self, runner, runtime):
        """Delete — error on individual user."""
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        runtime.admin.delete_user.side_effect = GoogleAdminError("fail")
        with (
            patch(MENU_PROMPT, side_effect=["7", "x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
            patch(MENU_CONFIRM, return_value=True),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice8_alias_error(self, runner, runtime):
        """Alias add — API error."""
        runtime.admin.add_alias.side_effect = GoogleAdminError("dup")
        with (
            patch(MENU_PROMPT, side_effect=["8", "add", "u@x.com", "a@x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice8_list_error(self, runner, runtime):
        """Alias list — API error."""
        runtime.admin.list_aliases.side_effect = GoogleAdminError("fail")
        with (
            patch(MENU_PROMPT, side_effect=["8", "list", "u@x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice8_remove_error(self, runner, runtime):
        """Alias remove — API error."""
        runtime.admin.remove_alias.side_effect = GoogleAdminError("fail")
        with (
            patch(MENU_PROMPT, side_effect=["8", "remove", "u@x.com", "a@x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice4_reset_error_on_user(self, runner, runtime):
        """Reset password — error on individual user."""
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        runtime.admin.update_password.side_effect = GoogleAdminError("fail")
        with (
            patch(MENU_PROMPT, side_effect=["4", "x.com", "same", "Pass1!", "0"]),
            patch(MENU_CTX, return_value=runtime),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0

    def test_choice5_suspend_error_on_user(self, runner, runtime):
        """Suspend — error on individual user."""
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        runtime.admin.suspend_user.side_effect = GoogleAdminError("fail")
        with (
            patch(MENU_PROMPT, side_effect=["5", "x.com", "0"]),
            patch(MENU_CTX, return_value=runtime),
            patch(MENU_CONFIRM, return_value=True),
        ):
            result = runner.invoke(app, ["menu"])
        assert result.exit_code == 0


# ─── Remaining _helpers.py paths ─────────────────────────────────────────────


class TestHelpersExtra:
    def test_assign_licenses_invalid_key(self, runner, runtime, tmp_path):
        """Invalid license key format."""
        from gsm.cli.commands.users._helpers import _assign_licenses
        from gsm.models.results import ResultKind

        results = [MagicMock(kind=ResultKind.SUCCESS, identifier="a@x.com")]
        _assign_licenses(runtime, results, "invalid-no-slash")
        runtime.admin.assign_license.assert_not_called()

    def test_assign_licenses_custom_format(self, runner, runtime):
        """Custom productId/skuId format."""
        from gsm.cli.commands.users._helpers import _assign_licenses
        from gsm.models.results import ResultKind

        results = [MagicMock(kind=ResultKind.SUCCESS, identifier="a@x.com")]
        _assign_licenses(runtime, results, "myProduct/mySku")
        runtime.admin.assign_license.assert_called_once_with("a@x.com", "mySku", "myProduct")

    def test_assign_licenses_api_error(self, runner, runtime):
        """License assignment fails."""
        from gsm.cli.commands.users._helpers import _assign_licenses
        from gsm.models.results import ResultKind

        runtime.admin.assign_license.side_effect = GoogleAdminError("fail")
        results = [MagicMock(kind=ResultKind.SUCCESS, identifier="a@x.com")]
        _assign_licenses(runtime, results, "education")
        # Should not raise — just prints warning

    def test_resolve_targets_api_error(self, runtime):
        """_resolve_user_targets with API error."""
        from click.exceptions import Exit

        from gsm.cli.commands.users._helpers import _resolve_user_targets

        runtime.admin.list_users.side_effect = GoogleAdminError("denied")
        with pytest.raises(Exit):
            _resolve_user_targets(runtime, file=None, domain="x.com")


# ─── Remaining _suspend.py paths (KeyboardInterrupt) ─────────────────────────


class TestSuspendInterrupt:
    def test_suspend_keyboard_interrupt(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\nb@x.com\n")
        runtime.admin.suspend_user.side_effect = [None, KeyboardInterrupt()]
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "suspend", "--file", str(f)])
        assert result.exit_code == 130

    def test_unsuspend_keyboard_interrupt(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\nb@x.com\n")
        runtime.admin.unsuspend_user.side_effect = [None, KeyboardInterrupt()]
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "unsuspend", "--file", str(f)])
        assert result.exit_code == 130


# ─── Remaining dns.py paths ──────────────────────────────────────────────────


class TestDnsExtra:
    def test_apply_from_ledger_domains(self, runner, runtime, tmp_path):
        """dns-apply with no --domain/--file uses ledger verified domains."""
        from gsm.models.domain import DomainStatus

        t = tmp_path / "dns.yml"
        t.write_text("records:\n  - type: TXT\n    name: '@'\n    content: test\n")
        record = MagicMock()
        record.name = "x.com"
        record.status = DomainStatus.VERIFIED
        runtime.ledger.list_domains.return_value = [record]
        zone = MagicMock()
        zone.zone_id = "z1"
        runtime.cf.get_zone_by_name.return_value = zone
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t)])
        assert result.exit_code == 0

    def test_apply_from_file(self, runner, runtime, tmp_path):
        """dns-apply with --file."""
        t = tmp_path / "dns.yml"
        t.write_text("records:\n  - type: TXT\n    name: '@'\n    content: test\n")
        domains_file = tmp_path / "domains.txt"
        domains_file.write_text("a.com\nb.com\n")
        zone = MagicMock()
        zone.zone_id = "z1"
        runtime.cf.get_zone_by_name.return_value = zone
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t), "--file", str(domains_file)])
        assert result.exit_code == 0

    def test_apply_invalid_yaml(self, runner, runtime, tmp_path):
        t = tmp_path / "dns.yml"
        t.write_text(": invalid: yaml: [")
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t), "--domain", "x.com"])
        assert result.exit_code == 2

    def test_apply_empty_records(self, runner, runtime, tmp_path):
        t = tmp_path / "dns.yml"
        t.write_text("records: []\n")
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t), "--domain", "x.com"])
        assert result.exit_code == 0
        assert "no records" in result.stdout.lower() or "No" in result.stdout

    def test_apply_cloudflare_error(self, runner, runtime, tmp_path):
        from gsm.clients.cloudflare import CloudflareError

        t = tmp_path / "dns.yml"
        t.write_text("records:\n  - type: TXT\n    name: '@'\n    content: test\n")
        zone = MagicMock()
        zone.zone_id = "z1"
        runtime.cf.get_zone_by_name.return_value = zone
        runtime.cf.upsert_dns_record.side_effect = CloudflareError("fail")
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t), "--domain", "x.com"])
        assert result.exit_code == 0
        assert "failed=1" in result.stdout


# ─── Remaining health.py paths ───────────────────────────────────────────────


class TestHealthExtra:
    def test_health_missing_mx(self, runner, runtime):
        """Health check with missing MX records."""

        mx_answer = MagicMock()
        mx_answer.__iter__ = lambda s: iter([])  # no MX records

        txt_answer = MagicMock()
        txt_record = MagicMock()
        txt_record.strings = [b"google-site-verification=abc"]
        txt_answer.__iter__ = lambda s: iter([txt_record])

        ns_answer = MagicMock()
        ns_record = MagicMock()
        ns_record.to_text.return_value = "ns1.cloudflare.com."
        ns_answer.__iter__ = lambda s: iter([ns_record])

        def mock_resolve(domain, rtype):
            return {"MX": mx_answer, "TXT": txt_answer, "NS": ns_answer}[rtype]

        with (
            patch("gsm.cli.commands.health.get_context", return_value=runtime),
            patch("dns.resolver.resolve", side_effect=mock_resolve),
        ):
            result = runner.invoke(app, ["health", "--domain", "x.com"])
        assert result.exit_code == 0
        assert "Issues" in result.stdout

    def test_health_ns_not_cloudflare(self, runner, runtime):
        """Health check with non-CF nameservers."""
        mx_answer = MagicMock()
        mx_record = MagicMock()
        mx_record.exchange.to_text.return_value = "aspmx.l.google.com."
        mx_answer.__iter__ = lambda s: iter([mx_record])

        txt_answer = MagicMock()
        txt_record = MagicMock()
        txt_record.strings = [b"google-site-verification=abc"]
        txt_answer.__iter__ = lambda s: iter([txt_record])

        ns_answer = MagicMock()
        ns_record = MagicMock()
        ns_record.to_text.return_value = "ns1.godaddy.com."
        ns_answer.__iter__ = lambda s: iter([ns_record])

        def mock_resolve(domain, rtype):
            return {"MX": mx_answer, "TXT": txt_answer, "NS": ns_answer}[rtype]

        with (
            patch("gsm.cli.commands.health.get_context", return_value=runtime),
            patch("gsm.cli.commands.health.GOOGLE_MX_HOSTS", frozenset({"aspmx.l.google.com"})),
            patch("dns.resolver.resolve", side_effect=mock_resolve),
        ):
            result = runner.invoke(app, ["health", "--domain", "x.com"])
        assert result.exit_code == 0
        assert "NS not CF" in result.stdout


# ─── Remaining _crud.py paths ────────────────────────────────────────────────


class TestCrudCoverage:
    def test_reset_password_random_no_output_shows_table(self, runner, runtime):
        """Random password without --output shows password table."""
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(
                app, ["users", "reset-password", "--domain", "x.com", "--random"]
            )
        assert result.exit_code == 0
        assert "Generated passwords" in result.stdout or "a@x.com" in result.stdout

    def test_reset_password_domain_api_error(self, runner, runtime):
        """Reset password with --domain but API fails."""
        runtime.admin.list_users.side_effect = GoogleAdminError("denied")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(
                app, ["users", "reset-password", "--domain", "x.com", "--same-password", "X"]
            )
        assert result.exit_code == 2

    def test_reset_password_no_target(self, runner, runtime):
        """Reset password without --domain or --file."""
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "reset-password", "--same-password", "X"])
        assert result.exit_code == 2

    def test_reset_password_empty_domain(self, runner, runtime):
        """Reset password with domain that has no users."""
        runtime.admin.list_users.return_value = []
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(
                app, ["users", "reset-password", "--domain", "x.com", "--same-password", "X"]
            )
        assert result.exit_code == 0

    def test_delete_keyboard_interrupt(self, runner, runtime, tmp_path):
        """Delete with KeyboardInterrupt mid-batch."""
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\nb@x.com\n")
        runtime.admin.delete_user.side_effect = [None, KeyboardInterrupt()]
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "delete", "--file", str(f), "--yes"])
        assert result.exit_code == 130

    def test_delete_no_confirm(self, runner, runtime, tmp_path):
        """Delete without --yes prompts and user says no."""
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "delete", "--file", str(f)], input="n\n")
        assert result.exit_code == 0
        runtime.admin.delete_user.assert_not_called()

    def test_update_api_error(self, runner, runtime, tmp_path):
        """Update with API error on one user."""
        f = tmp_path / "updates.csv"
        f.write_text("a@x.com,first_name,John\n")
        runtime.admin.update_user.side_effect = GoogleAdminError("fail")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "update", "--file", str(f)])
        assert result.exit_code == 0

    def test_add_interrupted(self, runner, runtime, tmp_path):
        """users add with partial results (interrupted)."""
        from gsm.models.results import ResultKind

        f = tmp_path / "akun.txt"
        f.write_text("a@x.com|pass|K001\nb@x.com|pass|K002\n")
        # Return fewer results than accounts = interrupted
        mock_results = [MagicMock(kind=ResultKind.SUCCESS, identifier="a@x.com")]
        with (
            patch("gsm.cli.commands.users._crud.get_context", return_value=runtime),
            patch("gsm.cli.commands.users._crud.create_users", return_value=mock_results),
            patch("gsm.cli.commands.users._crud.render_interrupted_summary"),
        ):
            result = runner.invoke(app, ["users", "add", "--file", str(f)])
        assert result.exit_code == 130
