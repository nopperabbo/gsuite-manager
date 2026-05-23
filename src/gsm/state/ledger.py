from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from gsm.models.domain import DomainRecord, DomainStatus
from gsm.models.user import UserRecord

__all__ = ["LEDGER_VERSION", "Ledger"]

_log = structlog.get_logger(__name__)

LEDGER_VERSION = 1


class Ledger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._domains: dict[str, DomainRecord] = {}
        self._users: dict[str, UserRecord] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            self._backup_corrupt_file()
            return
        if not isinstance(raw, dict):
            self._backup_corrupt_file()
            return
        for name, data in (raw.get("domains") or {}).items():
            try:
                self._domains[name] = DomainRecord.model_validate(data)
            except Exception as e:
                _log.warning("ledger_skip_corrupt_domain", domain=name, error=str(e))
                continue
        for email, data in (raw.get("users") or {}).items():
            try:
                self._users[email] = UserRecord.model_validate(data)
            except Exception as e:
                _log.warning("ledger_skip_corrupt_user", email=email, error=str(e))
                continue

    def _backup_corrupt_file(self) -> None:
        """Move corrupt ledger to <path>.corrupt-<ts> so user can recover.

        Better than silently overwriting - if our parser is wrong, the user's
        data is preserved. Persist() later will write a fresh ledger.
        """
        try:
            ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            backup = self._path.with_suffix(self._path.suffix + f".corrupt-{ts}")
            os.replace(self._path, backup)
            _log.warning("ledger_corrupt_backup", backup=str(backup))
        except OSError as e:
            _log.error("ledger_backup_failed", error=str(e))

    def _persist(self) -> None:
        payload: dict[str, Any] = {
            "version": LEDGER_VERSION,
            "domains": {k: v.model_dump(mode="json") for k, v in self._domains.items()},
            "users": {k: v.model_dump(mode="json") for k, v in self._users.items()},
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        os.replace(tmp, self._path)
        os.chmod(self._path, 0o600)

    def get_domain(self, name: str) -> DomainRecord | None:
        with self._lock:
            return self._domains.get(name)

    def upsert_domain(self, record: DomainRecord) -> None:
        with self._lock:
            existing = self._domains.get(record.name)
            if existing is not None:
                record.first_seen = existing.first_seen
            record.last_updated = datetime.now(UTC)
            self._domains[record.name] = record
            self._persist()

    def list_domains(self, status: DomainStatus | None = None) -> list[DomainRecord]:
        with self._lock:
            values = list(self._domains.values())
        if status is None:
            return values
        return [r for r in values if r.status == status]

    def get_user(self, email: str) -> UserRecord | None:
        with self._lock:
            return self._users.get(email)

    def upsert_user(self, record: UserRecord) -> None:
        with self._lock:
            existing = self._users.get(record.email)
            if existing is not None:
                record.first_seen = existing.first_seen
            record.last_updated = datetime.now(UTC)
            self._users[record.email] = record
            self._persist()

    def list_users(self, domain: str | None = None) -> list[UserRecord]:
        with self._lock:
            values = list(self._users.values())
        if domain is None:
            return values
        return [r for r in values if r.domain == domain]

    def archive(self, before: datetime, archive_path: Path) -> int:
        cutoff = before if before.tzinfo else before.replace(tzinfo=UTC)
        with self._lock:
            old_domains = {
                k: v
                for k, v in self._domains.items()
                if (
                    v.last_updated.replace(tzinfo=UTC)
                    if not v.last_updated.tzinfo
                    else v.last_updated
                )
                < cutoff
            }
            old_users = {
                k: v
                for k, v in self._users.items()
                if (
                    v.last_updated.replace(tzinfo=UTC)
                    if not v.last_updated.tzinfo
                    else v.last_updated
                )
                < cutoff
            }

            if not old_domains and not old_users:
                return 0

            archived_domains_dump = {k: v.model_dump(mode="json") for k, v in old_domains.items()}
            archived_users_dump = {k: v.model_dump(mode="json") for k, v in old_users.items()}

            existing_archive: dict[str, Any] = {}
            if archive_path.exists():
                try:
                    loaded = json.loads(archive_path.read_text())
                    if isinstance(loaded, dict):
                        existing_archive = loaded
                except (json.JSONDecodeError, OSError):
                    existing_archive = {}

            existing_domains = existing_archive.get("domains") or {}
            existing_users = existing_archive.get("users") or {}

            archive_data: dict[str, Any] = {
                "version": LEDGER_VERSION,
                "archived_at": datetime.now(UTC).isoformat(),
                "domains": {**existing_domains, **archived_domains_dump},
                "users": {**existing_users, **archived_users_dump},
            }

            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_tmp = archive_path.with_suffix(archive_path.suffix + ".tmp")
            archive_tmp.write_text(json.dumps(archive_data, indent=2, default=str))
            os.replace(archive_tmp, archive_path)

            for k in old_domains:
                self._domains.pop(k, None)
            for k in old_users:
                self._users.pop(k, None)
            self._persist()

            return len(old_domains) + len(old_users)

    def stats(self) -> dict[str, int]:
        with self._lock:
            domain_by_status: dict[str, int] = {}
            for d in self._domains.values():
                domain_by_status[d.status] = domain_by_status.get(d.status, 0) + 1
            user_by_status: dict[str, int] = {}
            for u in self._users.values():
                user_by_status[u.status] = user_by_status.get(u.status, 0) + 1
        return {
            "domains_total": len(self._domains),
            "users_total": len(self._users),
            **{f"domains_{k}": v for k, v in domain_by_status.items()},
            **{f"users_{k}": v for k, v in user_by_status.items()},
        }
