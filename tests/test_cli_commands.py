"""Comprehensive CLI command tests — covers users, groups, dns, health, expiry."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
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


# ─── Users: suspend / unsuspend ──────────────────────────────────────────────


class TestUsersSuspend:
    def test_suspend_with_file(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\nb@x.com\n")
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "suspend", "--file", str(f)])
        assert result.exit_code == 0
        assert runtime.admin.suspend_user.call_count == 2

    def test_suspend_dry_run(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\n")
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "suspend", "--file", str(f), "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        runtime.admin.suspend_user.assert_not_called()

    def test_suspend_error(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\n")
        runtime.admin.suspend_user.side_effect = GoogleAdminError("fail")
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "suspend", "--file", str(f)])
        assert result.exit_code == 0  # partial failure doesn't exit non-zero
        assert "0/1" in result.stdout

    def test_unsuspend_with_domain(self, runner, runtime):
        runtime.admin.list_users.return_value = [
            {"primaryEmail": "a@x.com"},
            {"primaryEmail": "b@x.com"},
        ]
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "unsuspend", "--domain", "x.com"])
        assert result.exit_code == 0
        assert runtime.admin.unsuspend_user.call_count == 2

    def test_unsuspend_dry_run(self, runner, runtime):
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "unsuspend", "--domain", "x.com", "--dry-run"])
        assert "dry-run" in result.stdout
        runtime.admin.unsuspend_user.assert_not_called()

    def test_no_target_exits(self, runner, runtime):
        with patch("gsm.cli.commands.users._suspend.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "suspend"])
        assert result.exit_code == 2


# ─── Users: audit ────────────────────────────────────────────────────────────


class TestUsersAudit:
    def _make_users(self, days_ago_list):
        now = datetime.now(UTC)
        users = []
        for d in days_ago_list:
            if d is None:
                users.append({"primaryEmail": "never@x.com", "lastLoginTime": ""})
            else:
                login = (now - timedelta(days=d)).isoformat()
                users.append({"primaryEmail": f"u{d}@x.com", "lastLoginTime": login})
        return users

    def test_audit_finds_inactive(self, runner, runtime):
        runtime.admin.list_users.return_value = self._make_users([5, 60, None])
        with patch("gsm.cli.commands.users._audit.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "audit", "--inactive-days", "30"])
        assert result.exit_code == 0
        assert "Inactive" in result.stdout

    def test_audit_all_active(self, runner, runtime):
        runtime.admin.list_users.return_value = self._make_users([1, 5, 10])
        with patch("gsm.cli.commands.users._audit.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "audit", "--inactive-days", "30"])
        assert result.exit_code == 0
        assert "All" in result.stdout

    def test_audit_json_output(self, runner, runtime):
        runtime.admin.list_users.return_value = self._make_users([60])
        with patch("gsm.cli.commands.users._audit.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "audit", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["inactive_count"] == 1

    def test_audit_saves_to_file(self, runner, runtime, tmp_path):
        runtime.admin.list_users.return_value = self._make_users([60])
        out = tmp_path / "inactive.txt"
        with patch("gsm.cli.commands.users._audit.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "audit", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_audit_api_error(self, runner, runtime):
        runtime.admin.list_users.side_effect = GoogleAdminError("denied")
        with patch("gsm.cli.commands.users._audit.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "audit"])
        assert result.exit_code == 2


# ─── Users: aliases ──────────────────────────────────────────────────────────


class TestUsersAliases:
    def test_alias_add_success(self, runner, runtime):
        with patch("gsm.cli.commands.users._aliases.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "alias-add", "user@x.com", "info@x.com"])
        assert result.exit_code == 0
        runtime.admin.add_alias.assert_called_once_with("user@x.com", "info@x.com")

    def test_alias_add_error(self, runner, runtime):
        runtime.admin.add_alias.side_effect = GoogleAdminError("dup")
        with patch("gsm.cli.commands.users._aliases.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "alias-add", "user@x.com", "info@x.com"])
        assert result.exit_code == 1

    def test_alias_list_success(self, runner, runtime):
        runtime.admin.list_aliases.return_value = ["info@x.com", "sales@x.com"]
        with patch("gsm.cli.commands.users._aliases.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "alias-list", "user@x.com"])
        assert result.exit_code == 0
        assert "info@x.com" in result.stdout

    def test_alias_list_empty(self, runner, runtime):
        runtime.admin.list_aliases.return_value = []
        with patch("gsm.cli.commands.users._aliases.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "alias-list", "user@x.com"])
        assert result.exit_code == 0
        assert "no aliases" in result.stdout

    def test_alias_remove_success(self, runner, runtime):
        with patch("gsm.cli.commands.users._aliases.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "alias-remove", "user@x.com", "info@x.com"])
        assert result.exit_code == 0
        runtime.admin.remove_alias.assert_called_once()

    def test_alias_remove_error(self, runner, runtime):
        runtime.admin.remove_alias.side_effect = GoogleAdminError("not found")
        with patch("gsm.cli.commands.users._aliases.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "alias-remove", "user@x.com", "info@x.com"])
        assert result.exit_code == 1


# ─── Users: CRUD ─────────────────────────────────────────────────────────────


class TestUsersCrud:
    def test_add_dry_run(self, runner, runtime, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("user@x.com|pass123|K001\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "add", "--file", str(f), "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.stdout

    def test_add_missing_file(self, runner, runtime):
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "add", "--file", "/no/such/file.txt"])
        assert result.exit_code != 0

    def test_list_empty_ledger(self, runner, runtime):
        runtime.ledger.list_users.return_value = []
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "list"])
        assert result.exit_code == 0
        assert "no users" in result.stdout

    def test_list_with_records(self, runner, runtime):
        record = MagicMock()
        record.email = "a@x.com"
        record.status = MagicMock(value="created")
        record.last_updated = datetime.now(UTC)
        record.last_error = None
        runtime.ledger.list_users.return_value = [record]
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "list"])
        assert result.exit_code == 0
        assert "a@x.com" in result.stdout

    def test_reset_password_same(self, runner, runtime):
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(
                app, ["users", "reset-password", "--domain", "x.com", "--same-password", "NewP@ss1"]
            )
        assert result.exit_code == 0
        runtime.admin.update_password.assert_called_once()

    def test_reset_password_random_with_output(self, runner, runtime, tmp_path):
        runtime.admin.list_users.return_value = [{"primaryEmail": "a@x.com"}]
        out = tmp_path / "creds.txt"
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(
                app,
                ["users", "reset-password", "--domain", "x.com", "--random", "--output", str(out)],
            )
        assert result.exit_code == 0
        assert out.exists()
        if sys.platform != "win32":
            assert out.stat().st_mode & 0o777 == 0o600

    def test_reset_password_no_mode_fails(self, runner, runtime):
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "reset-password", "--domain", "x.com"])
        assert result.exit_code == 2

    def test_move_success(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\nb@x.com\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "move", "--ou", "/Sales", "--file", str(f)])
        assert result.exit_code == 0
        assert runtime.admin.move_user_to_ou.call_count == 2

    def test_delete_dry_run(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "delete", "--file", str(f), "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        runtime.admin.delete_user.assert_not_called()

    def test_delete_with_yes(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "delete", "--file", str(f), "--yes"])
        assert result.exit_code == 0
        runtime.admin.delete_user.assert_called_once_with("a@x.com")

    def test_update_success(self, runner, runtime, tmp_path):
        f = tmp_path / "updates.csv"
        f.write_text("a@x.com,first_name,John\nb@x.com,department,Eng\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "update", "--file", str(f)])
        assert result.exit_code == 0
        assert runtime.admin.update_user.call_count == 2

    def test_update_empty_file(self, runner, runtime, tmp_path):
        f = tmp_path / "updates.csv"
        f.write_text("# comment only\n\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "update", "--file", str(f)])
        assert result.exit_code == 0
        assert "No valid" in result.stdout

    def test_update_file_not_found(self, runner, runtime):
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "update", "--file", "/no/such.csv"])
        assert result.exit_code == 2


# ─── Groups ──────────────────────────────────────────────────────────────────


class TestGroups:
    def test_create_success(self, runner, runtime):
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "create", "all@x.com", "--name", "All"])
        assert result.exit_code == 0
        runtime.admin.create_group.assert_called_once()

    def test_create_error(self, runner, runtime):
        runtime.admin.create_group.side_effect = GoogleAdminError("exists")
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "create", "all@x.com"])
        assert result.exit_code == 1

    def test_list_success(self, runner, runtime):
        runtime.admin.list_groups.return_value = [
            {"email": "all@x.com", "name": "All", "directMembersCount": 5}
        ]
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "list"])
        assert result.exit_code == 0
        assert "all@x.com" in result.stdout

    def test_list_empty(self, runner, runtime):
        runtime.admin.list_groups.return_value = []
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "list"])
        assert result.exit_code == 0
        assert "No groups" in result.stdout

    def test_add_member_single(self, runner, runtime):
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(
                app, ["groups", "add-member", "all@x.com", "--member", "user@x.com"]
            )
        assert result.exit_code == 0
        runtime.admin.add_group_member.assert_called_once()

    def test_add_member_from_file(self, runner, runtime, tmp_path):
        f = tmp_path / "members.txt"
        f.write_text("a@x.com\nb@x.com\n")
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "add-member", "all@x.com", "--file", str(f)])
        assert result.exit_code == 0
        assert runtime.admin.add_group_member.call_count == 2

    def test_add_member_no_target(self, runner, runtime):
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "add-member", "all@x.com"])
        assert result.exit_code == 2

    def test_remove_member(self, runner, runtime):
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "remove-member", "all@x.com", "user@x.com"])
        assert result.exit_code == 0
        runtime.admin.remove_group_member.assert_called_once()

    def test_members_list(self, runner, runtime):
        runtime.admin.list_group_members.return_value = [
            {"email": "a@x.com", "role": "MEMBER", "status": "ACTIVE"}
        ]
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "members", "all@x.com"])
        assert result.exit_code == 0
        assert "a@x.com" in result.stdout

    def test_members_empty(self, runner, runtime):
        runtime.admin.list_group_members.return_value = []
        with patch("gsm.cli.commands.groups.get_context", return_value=runtime):
            result = runner.invoke(app, ["groups", "members", "all@x.com"])
        assert result.exit_code == 0
        assert "no members" in result.stdout


# ─── DNS Apply ───────────────────────────────────────────────────────────────


class TestDnsApply:
    def _template(self, tmp_path):
        t = tmp_path / "dns.yml"
        t.write_text(
            "records:\n"
            "  - type: TXT\n"
            '    name: "@"\n'
            '    content: "v=spf1 include:_spf.google.com ~all"\n'
        )
        return t

    def test_dry_run(self, runner, runtime, tmp_path):
        t = self._template(tmp_path)
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t), "--domain", "x.com", "--dry-run"])
        assert result.exit_code == 0
        assert "would create" in result.stdout

    def test_apply_success(self, runner, runtime, tmp_path):
        t = self._template(tmp_path)
        zone = MagicMock()
        zone.zone_id = "z123"
        runtime.cf.get_zone_by_name.return_value = zone
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t), "--domain", "x.com"])
        assert result.exit_code == 0
        runtime.cf.upsert_dns_record.assert_called_once()

    def test_template_not_found(self, runner, runtime):
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", "/no/such.yml", "--domain", "x.com"])
        assert result.exit_code == 2

    def test_no_zone_found(self, runner, runtime, tmp_path):
        t = self._template(tmp_path)
        runtime.cf.get_zone_by_name.return_value = None
        with patch("gsm.cli.commands.dns.get_context", return_value=runtime):
            result = runner.invoke(app, ["dns-apply", str(t), "--domain", "x.com"])
        assert result.exit_code == 0
        assert "no CF zone" in result.stdout


# ─── Health ──────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_single_domain(self, runner, runtime):
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
        ns_record.to_text.return_value = "ns1.cloudflare.com."
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
        assert "Healthy: 1" in result.stdout

    def test_health_json_output(self, runner, runtime):
        import dns.resolver

        with (
            patch("gsm.cli.commands.health.get_context", return_value=runtime),
            patch("dns.resolver.resolve", side_effect=dns.resolver.NXDOMAIN()),
        ):
            result = runner.invoke(app, ["health", "--domain", "x.com", "--json"])
        assert result.exit_code == 0
        # stdout has Rich prefix text + JSON; extract JSON portion
        output = result.stdout
        json_start = output.index("{")
        data = json.loads(output[json_start:])
        assert data["healthy"] == 0
        assert data["issues_count"] == 1

    def test_health_no_verified_domains(self, runner, runtime):
        runtime.ledger.list_domains.return_value = []
        with patch("gsm.cli.commands.health.get_context", return_value=runtime):
            result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "No verified" in result.stdout


# ─── Check Expiry ────────────────────────────────────────────────────────────


class TestCheckExpiry:
    def test_expiry_domain_ok(self, runner, runtime):
        future = (datetime.now(UTC) + timedelta(days=365)).isoformat()
        rdap_response = MagicMock()
        rdap_response.read.return_value = json.dumps(
            {"events": [{"eventAction": "expiration", "eventDate": future}]}
        ).encode()
        rdap_response.__enter__ = lambda s: s
        rdap_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("gsm.cli.commands.expiry.get_context", return_value=runtime),
            patch("urllib.request.urlopen", return_value=rdap_response),
        ):
            result = runner.invoke(app, ["check-expiry", "--domain", "x.com"])
        assert result.exit_code == 0
        assert "No domains expiring" in result.stdout

    def test_expiry_domain_expiring(self, runner, runtime):
        soon = (datetime.now(UTC) + timedelta(days=10)).isoformat()
        rdap_response = MagicMock()
        rdap_response.read.return_value = json.dumps(
            {"events": [{"eventAction": "expiration", "eventDate": soon}]}
        ).encode()
        rdap_response.__enter__ = lambda s: s
        rdap_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("gsm.cli.commands.expiry.get_context", return_value=runtime),
            patch("urllib.request.urlopen", return_value=rdap_response),
        ):
            result = runner.invoke(app, ["check-expiry", "--domain", "x.com", "--days", "30"])
        assert result.exit_code == 0
        assert "Expiring" in result.stdout

    def test_expiry_json_output(self, runner, runtime):
        soon = (datetime.now(UTC) + timedelta(days=5)).isoformat()
        rdap_response = MagicMock()
        rdap_response.read.return_value = json.dumps(
            {"events": [{"eventAction": "expiration", "eventDate": soon}]}
        ).encode()
        rdap_response.__enter__ = lambda s: s
        rdap_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("gsm.cli.commands.expiry.get_context", return_value=runtime),
            patch("urllib.request.urlopen", return_value=rdap_response),
        ):
            result = runner.invoke(app, ["check-expiry", "--domain", "x.com", "--json"])
        assert result.exit_code == 0
        output = result.stdout
        json_start = output.index("{")
        data = json.loads(output[json_start:])
        assert data["expiring_count"] == 1

    def test_expiry_rdap_error(self, runner, runtime):
        import urllib.error

        with (
            patch("gsm.cli.commands.expiry.get_context", return_value=runtime),
            patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")),
        ):
            result = runner.invoke(app, ["check-expiry", "--domain", "x.com"])
        assert result.exit_code == 0
        assert "couldn't be checked" in result.stdout

    def test_expiry_no_verified_domains(self, runner, runtime):
        runtime.ledger.list_domains.return_value = []
        with patch("gsm.cli.commands.expiry.get_context", return_value=runtime):
            result = runner.invoke(app, ["check-expiry"])
        assert result.exit_code == 0
        assert "No verified" in result.stdout


# ─── Users: helpers ──────────────────────────────────────────────────────────


class TestUsersHelpers:
    def test_resolve_targets_from_file(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\nb@x.com\n")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "move", "--ou", "/X", "--file", str(f)])
        assert result.exit_code == 0

    def test_resolve_targets_no_input(self, runner, runtime):
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "move", "--ou", "/X"])
        assert result.exit_code == 2

    def test_assign_licenses_known_key(self, runner, runtime, tmp_path):
        from gsm.models.results import ResultKind

        f = tmp_path / "akun.txt"
        f.write_text("user@x.com|pass123|K001\n")

        mock_results = [MagicMock(kind=ResultKind.SUCCESS, identifier="user@x.com")]
        with (
            patch("gsm.cli.commands.users._crud.get_context", return_value=runtime),
            patch("gsm.cli.commands.users._crud.create_users", return_value=mock_results),
            patch("gsm.cli.commands.users._crud.render_results"),
        ):
            result = runner.invoke(
                app, ["users", "add", "--file", str(f), "--license", "education"]
            )
        assert result.exit_code == 0
        runtime.admin.assign_license.assert_called_once()


# ─── Go command ──────────────────────────────────────────────────────────────


class TestGoCommand:
    def test_go_no_files_found(self, runner, tmp_path):
        with patch("gsm.cli.commands.go._find_file", return_value=None):
            result = runner.invoke(app, ["go"])
        assert result.exit_code == 0
        assert "Gak nemu" in result.stdout

    def test_go_skip_both(self, runner, runtime, tmp_path):
        with (
            patch("gsm.cli.commands.go.get_context", return_value=runtime),
            patch("gsm.cli.commands.go._find_file", return_value=tmp_path / "x.txt"),
        ):
            result = runner.invoke(app, ["go", "--skip-domains", "--skip-users"])
        assert result.exit_code == 0

    def test_go_domains_only(self, runner, runtime, tmp_path):
        f = tmp_path / "domains.txt"
        f.write_text("test.com\nexample.com\n")
        mock_results = [MagicMock(kind=MagicMock(value="success"))]
        with (
            patch("gsm.cli.commands.go.get_context", return_value=runtime),
            patch("gsm.cli.commands.go.render_results"),
            patch("gsm.workflows.domain_onboarding.onboard_domains", return_value=mock_results),
        ):
            result = runner.invoke(app, ["go", "--domains", str(f), "--skip-users"])
        assert result.exit_code == 0

    def test_go_users_only(self, runner, runtime, tmp_path):
        f = tmp_path / "akun.txt"
        f.write_text("user@x.com|pass123|K001\n")
        mock_results = [MagicMock(kind=MagicMock(value="success"))]
        with (
            patch("gsm.cli.commands.go.get_context", return_value=runtime),
            patch("gsm.cli.commands.go.render_results"),
            patch("gsm.workflows.user_bulk_create.create_users", return_value=mock_results),
        ):
            result = runner.invoke(app, ["go", "--users", str(f), "--skip-domains"])
        assert result.exit_code == 0


# ─── Menu (skipped — fully interactive, requires Rich prompt mocking) ────────


# ─── Additional crud paths ───────────────────────────────────────────────────


class TestUsersCrudExtra:
    def test_reset_password_from_file(self, runner, runtime, tmp_path):
        emails_file = tmp_path / "emails.txt"
        emails_file.write_text("a@x.com\nb@x.com\n")
        out = tmp_path / "out.txt"
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(
                app,
                [
                    "users",
                    "reset-password",
                    "--file",
                    str(emails_file),
                    "--same-password",
                    "Pass123!",
                    "--output",
                    str(out),
                ],
            )
        assert result.exit_code == 0
        assert runtime.admin.update_password.call_count == 2
        assert out.exists()

    def test_reset_password_api_error(self, runner, runtime, tmp_path):
        emails_file = tmp_path / "emails.txt"
        emails_file.write_text("a@x.com\n")
        runtime.admin.update_password.side_effect = GoogleAdminError("fail")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(
                app,
                ["users", "reset-password", "--file", str(emails_file), "--same-password", "X"],
            )
        assert result.exit_code == 0
        assert "failed=1" in result.stdout

    def test_move_api_error(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\n")
        runtime.admin.move_user_to_ou.side_effect = GoogleAdminError("denied")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "move", "--ou", "/X", "--file", str(f)])
        assert result.exit_code == 0

    def test_delete_api_error(self, runner, runtime, tmp_path):
        f = tmp_path / "emails.txt"
        f.write_text("a@x.com\n")
        runtime.admin.delete_user.side_effect = GoogleAdminError("nope")
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "delete", "--file", str(f), "--yes"])
        assert result.exit_code == 0

    def test_list_filter_by_status(self, runner, runtime):
        record = MagicMock()
        record.email = "a@x.com"
        record.status = MagicMock(value="created")
        record.last_updated = datetime.now(UTC)
        record.last_error = None
        runtime.ledger.list_users.return_value = [record]
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "list", "--status", "created"])
        assert result.exit_code == 0

    def test_list_filter_by_domain(self, runner, runtime):
        runtime.ledger.list_users.return_value = []
        with patch("gsm.cli.commands.users._crud.get_context", return_value=runtime):
            result = runner.invoke(app, ["users", "list", "--domain", "x.com"])
        assert result.exit_code == 0

    def test_add_success_with_results(self, runner, runtime, tmp_path):
        from gsm.models.results import ResultKind

        f = tmp_path / "akun.txt"
        f.write_text("a@x.com|pass123|K001\nb@x.com|pass456|K002\n")
        mock_results = [
            MagicMock(kind=ResultKind.SUCCESS, identifier="a@x.com"),
            MagicMock(kind=ResultKind.FAILED, identifier="b@x.com"),
        ]
        with (
            patch("gsm.cli.commands.users._crud.get_context", return_value=runtime),
            patch("gsm.cli.commands.users._crud.create_users", return_value=mock_results),
            patch("gsm.cli.commands.users._crud.render_results"),
        ):
            result = runner.invoke(app, ["users", "add", "--file", str(f)])
        assert result.exit_code == 1  # has failures
