"""User bulk creation workflow.

Reads accounts from `akun.txt`-style file (legacy format `email|password|kode`)
and creates Workspace users idempotently.

Notes on porting from legacy:
- Legacy resolved akun.txt via `os.path.dirname(SCRIPT_DIR)` (parent of script
  dir) which was a known bug. We resolve relative to CWD instead and let the
  caller pass an explicit path.
- Legacy hardcoded a list of ~200 common first names to split usernames; we
  drop that heuristic and use a simpler rule: if the local-part contains '.',
  split on it; otherwise first_name=local-part, last_name="User". Names are
  not used by Workspace for anything authoritative anyway - the
  primaryEmail is the identity.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr

from gsm.clients.google_admin import GoogleAdminClient, GoogleAdminError
from gsm.core.auth import AuthError
from gsm.core.config import Settings
from gsm.core.errors import humanize
from gsm.core.logging import get_logger
from gsm.models.results import ItemResult
from gsm.models.user import AccountSpec, UserRecord, UserStatus
from gsm.state.ledger import Ledger


def parse_akun_file(path: Path) -> list[AccountSpec]:
    """Parse `akun.txt` format: `email | password | extra_code` (one per line).

    Lines without '@' or with fewer than 2 pipe-separated fields are skipped
    (matches legacy behavior). Comments (#-prefixed) and blank lines are skipped.
    """
    if not path.exists():
        raise FileNotFoundError(f"accounts file not found: {path}")

    accounts: list[AccountSpec] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "@" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue
            email = parts[0]
            password = parts[1]
            extra = parts[2] if len(parts) >= 3 else None
            if not _is_valid_email(email) or not password:
                continue
            first, last = _split_name(email)
            accounts.append(
                AccountSpec(
                    email=email,
                    password=SecretStr(password),
                    first_name=first,
                    last_name=last,
                    extra_code=extra,
                )
            )
    return accounts


def _is_valid_email(email: str) -> bool:
    if "@" not in email:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and bool(domain) and "." in domain


def _split_name(email: str) -> tuple[str, str]:
    local = email.split("@", 1)[0]
    if "." in local:
        first, _, last = local.partition(".")
        return first.capitalize(), last.capitalize()
    return local.capitalize(), "User"


class UserBulkCreator:
    """Stateful bulk user creator."""

    def __init__(
        self,
        *,
        settings: Settings,
        ledger: Ledger,
        admin: GoogleAdminClient,
    ) -> None:
        self._settings = settings
        self._ledger = ledger
        self._admin = admin
        self._log = get_logger("workflow.user_bulk_create")

    def run(self, account: AccountSpec) -> ItemResult:
        existing = self._ledger.get_user(account.email)
        if existing and existing.status is UserStatus.CREATED:
            return ItemResult.skipped(
                account.email,
                "already created",
                status=existing.status.value,
            )

        record = existing or UserRecord(
            email=account.email,
            status=UserStatus.PENDING,
        )
        try:
            self._admin.create_user(
                email=account.email,
                password=account.password.get_secret_value(),
                first_name=account.first_name or "User",
                last_name=account.last_name or "User",
            )
            record.status = UserStatus.CREATED
            record.last_error = None
            record.last_updated = datetime.now(UTC)
            self._ledger.upsert_user(record)
            return ItemResult.success(
                account.email, "created", status=record.status.value
            )
        except (AuthError, GoogleAdminError) as e:
            friendly = humanize(e).render()
            record.status = UserStatus.FAILED
            record.last_error = friendly
            record.last_updated = datetime.now(UTC)
            self._ledger.upsert_user(record)
            self._log.error(
                "user_create_failed", email=account.email, error=str(e)
            )
            return ItemResult.failed(
                account.email, friendly, status=record.status.value
            )


def create_users(
    accounts: list[AccountSpec],
    *,
    settings: Settings,
    ledger: Ledger,
    admin: GoogleAdminClient,
    delay_per_user_sec: float | None = None,
    on_progress: Callable[[int, int, str, ItemResult], None] | None = None,
) -> list[ItemResult]:
    """Sequential bulk creation. Sleeps between users by configured delay.

    on_progress(index, total, email, result) called after each user.
    """
    creator = UserBulkCreator(settings=settings, ledger=ledger, admin=admin)
    delay = (
        delay_per_user_sec
        if delay_per_user_sec is not None
        else settings.delay_per_user_sec
    )
    results: list[ItemResult] = []
    total = len(accounts)
    for idx, account in enumerate(accounts):
        result = creator.run(account)
        results.append(result)
        if on_progress is not None:
            on_progress(idx + 1, total, account.email, result)
        if idx < total - 1 and delay > 0:
            time.sleep(delay)
    return results
