"""pytest configuration and shared fixtures.

Ensures src/ is on path even when editable install fails (Python pth-file
quirk with spaces in paths). Provides reusable fixtures for Settings and
mock clients used across multiple test modules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Force Rich/Typer to disable color output in tests (prevents ANSI escape codes
# from breaking string assertions in CI where NO_COLOR may not propagate to
# CliRunner subprocesses).
os.environ.setdefault("NO_COLOR", "1")
os.environ.setdefault("TERM", "dumb")


@pytest.fixture
def settings(tmp_path):
    """Standard Settings fixture with dummy credentials for unit tests."""
    from gsm.core.config import Settings

    return Settings(
        cf_api_token="dummy-token",
        cf_account_id="0061a056f8cbc860fb9ec99bd41a0ccc",
        google_oauth_client_path=tmp_path / "credentials.json",
        google_oauth_token_path=tmp_path / "token.json",
        ledger_path=tmp_path / "gsm_state.json",
    )


@pytest.fixture
def mock_admin():
    """Mock GoogleAdminClient with all methods returning success defaults."""
    admin = MagicMock()
    admin.list_users.return_value = []
    admin.list_domains.return_value = []
    admin.list_groups.return_value = []
    return admin


@pytest.fixture
def mock_cf():
    """Mock CloudflareClient."""
    cf = MagicMock()
    cf.ensure_zone.return_value = ("zone-id", ["ns1.cf.com", "ns2.cf.com"])
    return cf


@pytest.fixture
def mock_verify():
    """Mock Google Site Verification client."""
    return MagicMock()


@pytest.fixture
def ledger(tmp_path, settings):
    """Fresh Ledger instance backed by a temp file."""
    from gsm.state.ledger import Ledger

    return Ledger(settings.ledger_path)
