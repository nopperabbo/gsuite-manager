"""End-to-end tests for `gsm audit` command (with mocked CF + Workspace)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsm.cli import app
from gsm.clients.cloudflare import ZoneInfo


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("GSM_CF_API_TOKEN", "test-token")
    monkeypatch.setenv(
        "GSM_CF_ACCOUNT_ID", "0061a056f8cbc860fb9ec99bd41a0ccc"
    )
    monkeypatch.setenv(
        "GSM_GOOGLE_OAUTH_CLIENT_PATH", str(tmp_path / "credentials.json")
    )
    monkeypatch.setenv(
        "GSM_GOOGLE_OAUTH_TOKEN_PATH", str(tmp_path / "token.json")
    )
    monkeypatch.setenv("GSM_LEDGER_PATH", str(tmp_path / "gsm_state.json"))
    return tmp_path


def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(zone_id=f"id-{name}", name=name, nameservers=[], created=False)


class TestAuditCommand:
    def test_all_synced_no_gaps(self, runner, env):
        cf = MagicMock()
        cf.list_zones.return_value = [_zone("a.com"), _zone("b.com")]
        admin = MagicMock()
        admin.list_domains.return_value = [
            {"domainName": "a.com", "verified": True},
            {"domainName": "b.com", "verified": True},
        ]
        with patch("gsm.cli._shared.CloudflareClient", return_value=cf), patch(
            "gsm.cli._shared.GoogleAdminClient", return_value=admin
        ):
            result = runner.invoke(app, ["audit"])
        assert result.exit_code == 0
        assert "udah sinkron" in result.output

    def test_cf_only_gap_detected(self, runner, env):
        cf = MagicMock()
        cf.list_zones.return_value = [
            _zone("synced.com"),
            _zone("missing-from-ws.com"),
            _zone("another-gap.com"),
        ]
        admin = MagicMock()
        admin.list_domains.return_value = [
            {"domainName": "synced.com", "verified": True},
        ]
        with patch("gsm.cli._shared.CloudflareClient", return_value=cf), patch(
            "gsm.cli._shared.GoogleAdminClient", return_value=admin
        ):
            result = runner.invoke(app, ["audit"])
        assert result.exit_code == 0
        assert "missing-from-ws.com" in result.output
        assert "another-gap.com" in result.output
        assert "2" in result.output

    def test_workspace_only_gap_detected(self, runner, env):
        cf = MagicMock()
        cf.list_zones.return_value = [_zone("a.com")]
        admin = MagicMock()
        admin.list_domains.return_value = [
            {"domainName": "a.com", "verified": True},
            {"domainName": "no-cf-zone.com", "verified": True},
        ]
        with patch("gsm.cli._shared.CloudflareClient", return_value=cf), patch(
            "gsm.cli._shared.GoogleAdminClient", return_value=admin
        ):
            result = runner.invoke(app, ["audit"])
        assert result.exit_code == 0
        assert "no-cf-zone.com" in result.output

    def test_unverified_in_workspace(self, runner, env):
        cf = MagicMock()
        cf.list_zones.return_value = [_zone("pending.com")]
        admin = MagicMock()
        admin.list_domains.return_value = [
            {"domainName": "pending.com", "verified": False},
        ]
        with patch("gsm.cli._shared.CloudflareClient", return_value=cf), patch(
            "gsm.cli._shared.GoogleAdminClient", return_value=admin
        ):
            result = runner.invoke(app, ["audit"])
        assert result.exit_code == 0
        assert "verify --only-pending" in result.output

    def test_output_file_written(self, runner, env, tmp_path):
        cf = MagicMock()
        cf.list_zones.return_value = [_zone("gap1.com"), _zone("gap2.com")]
        admin = MagicMock()
        admin.list_domains.return_value = []
        out_file = tmp_path / "gaps.txt"
        with patch("gsm.cli._shared.CloudflareClient", return_value=cf), patch(
            "gsm.cli._shared.GoogleAdminClient", return_value=admin
        ):
            result = runner.invoke(
                app, ["audit", "--output", str(out_file)]
            )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "gap1.com" in content
        assert "gap2.com" in content

    def test_show_synced_lists_them(self, runner, env):
        cf = MagicMock()
        cf.list_zones.return_value = [_zone("a.com")]
        admin = MagicMock()
        admin.list_domains.return_value = [
            {"domainName": "a.com", "verified": True},
        ]
        with patch("gsm.cli._shared.CloudflareClient", return_value=cf), patch(
            "gsm.cli._shared.GoogleAdminClient", return_value=admin
        ):
            result = runner.invoke(app, ["audit", "--show-synced"])
        assert result.exit_code == 0
        assert "✓" in result.output or "a.com" in result.output

    def test_cf_error_exits_with_friendly_message(self, runner, env):
        from gsm.clients.cloudflare import CloudflareError

        cf = MagicMock()
        cf.list_zones.side_effect = CloudflareError("Invalid API Token")
        admin = MagicMock()
        with patch("gsm.cli._shared.CloudflareClient", return_value=cf), patch(
            "gsm.cli._shared.GoogleAdminClient", return_value=admin
        ):
            result = runner.invoke(app, ["audit"])
        assert result.exit_code == 2
        assert "Traceback" not in result.output


class TestListZones:
    def test_list_zones_paginates(self):
        from pydantic import SecretStr

        from gsm.clients.cloudflare import CloudflareClient
        from gsm.core.config import Settings

        s = Settings(
            cf_api_token=SecretStr("test"),
            cf_account_id="0061a056f8cbc860fb9ec99bd41a0ccc",
        )
        client = CloudflareClient(s)

        page1 = MagicMock()
        page1.json.return_value = {
            "success": True,
            "result": [
                {"id": "z1", "name": "a.com", "name_servers": []},
                {"id": "z2", "name": "b.com", "name_servers": []},
            ],
            "result_info": {"total_pages": 2, "page": 1},
        }
        page2 = MagicMock()
        page2.json.return_value = {
            "success": True,
            "result": [{"id": "z3", "name": "c.com", "name_servers": []}],
            "result_info": {"total_pages": 2, "page": 2},
        }
        with patch.object(
            client._session,
            "request",
            side_effect=[page1, page2],
        ):
            zones = client.list_zones()
        assert len(zones) == 3
        names = {z.name for z in zones}
        assert names == {"a.com", "b.com", "c.com"}

    def test_list_zones_empty(self):
        from pydantic import SecretStr

        from gsm.clients.cloudflare import CloudflareClient
        from gsm.core.config import Settings

        s = Settings(
            cf_api_token=SecretStr("test"),
            cf_account_id="0061a056f8cbc860fb9ec99bd41a0ccc",
        )
        client = CloudflareClient(s)
        empty_resp = MagicMock()
        empty_resp.json.return_value = {
            "success": True,
            "result": [],
            "result_info": {"total_pages": 1, "page": 1},
        }
        with patch.object(client._session, "request", return_value=empty_resp):
            zones = client.list_zones()
        assert zones == []
