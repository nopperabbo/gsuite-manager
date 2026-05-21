from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, SecretStr

__all__ = ["AccountSpec", "UserRecord", "UserStatus"]


class UserStatus(StrEnum):
    PENDING = "pending"
    CREATED = "created"
    FAILED = "failed"


class AccountSpec(BaseModel):
    email: str
    password: SecretStr
    first_name: str | None = None
    last_name: str | None = None
    extra_code: str | None = None


class UserRecord(BaseModel):
    email: str
    status: UserStatus = UserStatus.PENDING
    first_name: str | None = None
    last_name: str | None = None
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_error: str | None = None

    @property
    def domain(self) -> str:
        return self.email.split("@", 1)[1] if "@" in self.email else ""

    def touch(self) -> None:
        self.last_updated = datetime.now(UTC)
