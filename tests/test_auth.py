from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gsm.core.auth import AuthError, OAuthDesktopAuth, detect_oauth_client_file
from gsm.core.config import Settings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("GSM_CF_API_TOKEN", "test")
    monkeypatch.setenv("GSM_CF_ACCOUNT_ID", "0061a056f8cbc860fb9ec99bd41a0ccc")
    monkeypatch.setenv("GSM_GOOGLE_OAUTH_CLIENT_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("GSM_GOOGLE_OAUTH_TOKEN_PATH", str(tmp_path / "token.json"))
    return Settings()  # type: ignore[call-arg]


def _make_creds(*, valid: bool = True, expired: bool = False, has_refresh: bool = True) -> MagicMock:
    creds = MagicMock()
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = "refresh" if has_refresh else None
    creds.to_json.return_value = '{"token": "abc"}'
    return creds


class TestLoadCachedToken:
    def test_returns_valid_cached_creds(self, settings: Settings, tmp_path: Path) -> None:
        (tmp_path / "token.json").write_text('{"token": "abc"}')
        with patch("gsm.core.auth.Credentials.from_authorized_user_file") as mock_load:
            mock_load.return_value = _make_creds(valid=True)
            auth = OAuthDesktopAuth(settings)
            creds = auth.get_credentials()
            assert creds.valid
            mock_load.assert_called_once()

    def test_refreshes_expired_with_refresh_token(self, settings: Settings, tmp_path: Path) -> None:
        (tmp_path / "token.json").write_text('{"token": "abc"}')
        expired = _make_creds(valid=False, expired=True, has_refresh=True)

        def make_valid_after_refresh(_req: object) -> None:
            expired.valid = True

        expired.refresh.side_effect = make_valid_after_refresh

        with patch("gsm.core.auth.Credentials.from_authorized_user_file", return_value=expired):
            auth = OAuthDesktopAuth(settings)
            auth.get_credentials()
            expired.refresh.assert_called_once()

    def test_corrupt_token_falls_back_to_browser_flow(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        (tmp_path / "token.json").write_text("not valid json")
        (tmp_path / "credentials.json").write_text('{"installed": {"client_id": "x"}}')

        with (
            patch(
                "gsm.core.auth.Credentials.from_authorized_user_file",
                side_effect=ValueError("corrupt"),
            ),
            patch("gsm.core.auth.InstalledAppFlow.from_client_secrets_file") as flow_factory,
        ):
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = _make_creds(valid=True)
            flow_factory.return_value = mock_flow

            auth = OAuthDesktopAuth(settings)
            auth.get_credentials()
            mock_flow.run_local_server.assert_called_once()


class TestBrowserFlow:
    def test_triggers_browser_when_no_token(self, settings: Settings, tmp_path: Path) -> None:
        (tmp_path / "credentials.json").write_text('{"installed": {"client_id": "x"}}')
        with patch("gsm.core.auth.InstalledAppFlow.from_client_secrets_file") as flow_factory:
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = _make_creds(valid=True)
            flow_factory.return_value = mock_flow

            auth = OAuthDesktopAuth(settings)
            auth.get_credentials()

            mock_flow.run_local_server.assert_called_once_with(port=0)
            assert (tmp_path / "token.json").exists()

    def test_raises_when_client_path_missing(self, settings: Settings) -> None:
        auth = OAuthDesktopAuth(settings)
        with pytest.raises(AuthError, match="OAuth client file not found"):
            auth.get_credentials()


class TestTokenPersistence:
    def test_token_written_atomically_with_mode_600(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        (tmp_path / "credentials.json").write_text('{"installed": {"client_id": "x"}}')
        with patch("gsm.core.auth.InstalledAppFlow.from_client_secrets_file") as flow_factory:
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = _make_creds(valid=True)
            flow_factory.return_value = mock_flow

            auth = OAuthDesktopAuth(settings)
            auth.get_credentials()

            token_file = tmp_path / "token.json"
            assert token_file.exists()
            mode = token_file.stat().st_mode & 0o777
            assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


class TestServiceBuilders:
    def test_build_admin_and_verify_use_same_creds(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        (tmp_path / "token.json").write_text('{"token": "abc"}')
        with (
            patch("gsm.core.auth.Credentials.from_authorized_user_file") as mock_load,
            patch("gsm.core.auth.build") as mock_build,
        ):
            mock_load.return_value = _make_creds(valid=True)
            mock_build.return_value = MagicMock()

            auth = OAuthDesktopAuth(settings)
            auth.build_admin_service()
            auth.build_verify_service()

            assert mock_build.call_count == 2
            assert mock_build.call_args_list[0][0][0] == "admin"
            assert mock_build.call_args_list[1][0][0] == "siteVerification"


class TestThreadSafety:
    def test_concurrent_get_credentials_refreshes_once(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        (tmp_path / "token.json").write_text('{"token": "abc"}')
        load_count = 0

        def fake_load(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal load_count
            load_count += 1
            return _make_creds(valid=True)

        with patch("gsm.core.auth.Credentials.from_authorized_user_file", side_effect=fake_load):
            auth = OAuthDesktopAuth(settings)
            results: list[object] = []

            def worker() -> None:
                results.append(auth.get_credentials())

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(results) == 8
            assert load_count == 1


class TestDetectClientFile:
    def test_prefers_credentials_json(self, tmp_path: Path) -> None:
        (tmp_path / "credentials.json").write_text("{}")
        (tmp_path / "client_secret_abc.json").write_text("{}")
        assert detect_oauth_client_file(tmp_path) == tmp_path / "credentials.json"

    def test_falls_back_to_client_secret(self, tmp_path: Path) -> None:
        (tmp_path / "client_secret_xyz.json").write_text("{}")
        assert detect_oauth_client_file(tmp_path) == tmp_path / "client_secret_xyz.json"

    def test_returns_none_when_neither_exists(self, tmp_path: Path) -> None:
        assert detect_oauth_client_file(tmp_path) is None
