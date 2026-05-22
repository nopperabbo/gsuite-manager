from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gsm.core.config import Settings, load_settings

VALID_CF_TOKEN = "test-token-not-real"
VALID_CF_ACCOUNT_ID = "0061a056f8cbc860fb9ec99bd41a0ccc"


def _write_env(tmp_path: Path, **overrides: str) -> Path:
    base = {
        "GSM_CF_API_TOKEN": VALID_CF_TOKEN,
        "GSM_CF_ACCOUNT_ID": VALID_CF_ACCOUNT_ID,
    }
    base.update(overrides)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in base.items()))
    return env_file


class TestCsvListParsing:
    """The critical .env-friendly behavior: list fields accept comma-separated strings.

    Pydantic-settings would otherwise try JSON-decode list fields, which makes
    `GSM_DNS_CHECK_RESOLVERS=8.8.8.8,1.1.1.1` fail in production .env files.
    """

    def test_resolvers_accept_csv(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_RESOLVERS="8.8.8.8,1.1.1.1,9.9.9.9")
        settings = load_settings(env_file=env_file)
        assert settings.dns_check_resolvers == ["8.8.8.8", "1.1.1.1", "9.9.9.9"]

    def test_resolvers_csv_strips_whitespace(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_RESOLVERS="8.8.8.8 , 1.1.1.1 ,  9.9.9.9")
        settings = load_settings(env_file=env_file)
        assert settings.dns_check_resolvers == ["8.8.8.8", "1.1.1.1", "9.9.9.9"]

    def test_resolvers_csv_skips_empty_segments(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_RESOLVERS="8.8.8.8,,1.1.1.1,")
        settings = load_settings(env_file=env_file)
        assert settings.dns_check_resolvers == ["8.8.8.8", "1.1.1.1"]

    def test_resolvers_default_when_unset(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path)
        settings = load_settings(env_file=env_file)
        assert settings.dns_check_resolvers == ["8.8.8.8", "1.1.1.1"]

    def test_backoff_accepts_csv_ints(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_BACKOFF_SEC="10,20,30,45,60")
        settings = load_settings(env_file=env_file)
        assert settings.dns_check_backoff_sec == [10, 20, 30, 45, 60]

    def test_backoff_csv_strips_whitespace(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_BACKOFF_SEC=" 5 , 10 , 15 ")
        settings = load_settings(env_file=env_file)
        assert settings.dns_check_backoff_sec == [5, 10, 15]

    def test_backoff_rejects_zero(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_BACKOFF_SEC="10,0,30")
        with pytest.raises(ValidationError) as exc:
            load_settings(env_file=env_file)
        assert "positive" in str(exc.value)

    def test_backoff_rejects_negative(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_BACKOFF_SEC="10,-5,30")
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)

    def test_backoff_rejects_non_integer(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_BACKOFF_SEC="10,abc,30")
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)


class TestSettingsLoad:
    def test_load_from_env_file(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path)
        settings = load_settings(env_file=env_file)
        assert settings.cf_api_token.get_secret_value() == VALID_CF_TOKEN
        assert settings.cf_account_id == VALID_CF_ACCOUNT_ID

    def test_load_from_env_vars(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GSM_CF_API_TOKEN", VALID_CF_TOKEN)
        monkeypatch.setenv("GSM_CF_ACCOUNT_ID", VALID_CF_ACCOUNT_ID)
        settings = Settings()  # type: ignore[call-arg]
        assert settings.cf_account_id == VALID_CF_ACCOUNT_ID

    def test_defaults_applied(self, tmp_path: Path) -> None:
        settings = load_settings(env_file=_write_env(tmp_path))
        assert settings.delay_per_domain_sec == 3.0
        assert settings.dns_check_resolvers == ["8.8.8.8", "1.1.1.1"]
        assert settings.log_level == "INFO"
        assert settings.log_format == "console"


class TestValidation:
    def test_invalid_cf_account_id_length(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_CF_ACCOUNT_ID="short")
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)

    def test_invalid_cf_account_id_non_hex(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_CF_ACCOUNT_ID="z" * 32)
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)

    def test_invalid_log_level(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_LOG_LEVEL="VERBOSE")
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)

    def test_invalid_log_format(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_LOG_FORMAT="xml")
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)

    def test_log_level_normalized_uppercase(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_LOG_LEVEL="debug")
        settings = load_settings(env_file=env_file)
        assert settings.log_level == "DEBUG"

    def test_invalid_negative_delay(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DELAY_PER_DOMAIN_SEC="-1")
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)

    def test_empty_backoff_list(self, tmp_path: Path) -> None:
        env_file = _write_env(tmp_path, GSM_DNS_CHECK_BACKOFF_SEC="[]")
        with pytest.raises(ValidationError):
            load_settings(env_file=env_file)


class TestSecretMasking:
    def test_secret_str_repr_masked(self, tmp_path: Path) -> None:
        settings = load_settings(env_file=_write_env(tmp_path))
        repr_str = repr(settings)
        assert VALID_CF_TOKEN not in repr_str
        assert "SecretStr" in repr_str

    def test_model_dump_excludes_secret(self, tmp_path: Path) -> None:
        settings = load_settings(env_file=_write_env(tmp_path))
        dumped = settings.model_dump()
        assert dumped["cf_api_token"].get_secret_value() == VALID_CF_TOKEN
        json_dump = settings.model_dump(mode="json")
        assert json_dump["cf_api_token"] == "**********"


class TestMissingRequired:
    def test_missing_cf_token_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        for var in ("GSM_CF_API_TOKEN", "GSM_CF_ACCOUNT_ID"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]
