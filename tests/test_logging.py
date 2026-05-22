from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest
import structlog

from gsm.core.config import Settings
from gsm.core.logging import (
    LEGACY_PREFIXES,
    configure_logging,
    get_logger,
    legacy_log,
)


@pytest.fixture
def settings_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("GSM_CF_API_TOKEN", "test")
    monkeypatch.setenv("GSM_CF_ACCOUNT_ID", "0061a056f8cbc860fb9ec99bd41a0ccc")

    def make(log_format: str = "console", log_level: str = "INFO") -> Settings:
        monkeypatch.setenv("GSM_LOG_FORMAT", log_format)
        monkeypatch.setenv("GSM_LOG_LEVEL", log_level)
        return Settings()  # type: ignore[call-arg]

    return make


@pytest.fixture(autouse=True)
def reset_structlog():
    yield
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


class TestConfigure:
    def test_console_format_emits_pretty_output(
        self, settings_factory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(settings_factory(log_format="console"))
        log = get_logger("test")
        log.info("hello world", domain="bunhe.tech")

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "hello world" in combined
        assert "bunhe.tech" in combined

    def test_json_format_emits_parseable_json(
        self, settings_factory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(settings_factory(log_format="json"))
        log = get_logger("test")
        log.info("event_message", count=42)

        captured = capsys.readouterr()
        line = (captured.out + captured.err).strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["event"] == "event_message"
        assert parsed["count"] == 42
        assert parsed["level"] == "info"
        assert "timestamp" in parsed

    def test_log_level_filters_debug(
        self, settings_factory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(settings_factory(log_format="json", log_level="INFO"))
        log = get_logger()
        log.debug("hidden")
        log.info("visible")

        out = capsys.readouterr().out + capsys.readouterr().err
        assert "visible" in out
        assert "hidden" not in out


class TestLegacyLog:
    @pytest.mark.parametrize("status,prefix", list(LEGACY_PREFIXES.items()))
    def test_emits_correct_prefix(
        self, status: str, prefix: str, capsys: pytest.CaptureFixture[str], settings_factory
    ) -> None:
        configure_logging(settings_factory())
        legacy_log(status, "test message")
        out = capsys.readouterr().out
        assert prefix in out
        assert "test message" in out
        assert re.match(r"^\d{2}:\d{2}:\d{2}", out.strip())

    def test_unknown_status_uses_question_mark(
        self, capsys: pytest.CaptureFixture[str], settings_factory
    ) -> None:
        configure_logging(settings_factory())
        legacy_log("mystery", "weird")
        assert "[?]" in capsys.readouterr().out


class TestTimestamp:
    def test_iso_timestamp_present(
        self, settings_factory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(settings_factory(log_format="json"))
        log = get_logger()
        log.info("test")
        line = (capsys.readouterr().out + capsys.readouterr().err).strip().splitlines()[-1]
        parsed = json.loads(line)
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", parsed["timestamp"])
