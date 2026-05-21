from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

__all__ = ["DomainRecord", "DomainStatus"]


class DomainStatus(StrEnum):
    PENDING = "pending"
    GSUITE_ADDED = "gsuite_added"
    TOKEN_FETCHED = "token_fetched"
    CF_ZONE_READY = "cf_zone_ready"
    DNS_INJECTED = "dns_injected"
    DNS_PENDING = "dns_pending"
    VERIFIED = "verified"
    FAILED = "failed"


class DomainRecord(BaseModel):
    name: str
    status: DomainStatus = DomainStatus.PENDING
    cf_zone_id: str | None = None
    cf_nameservers: list[str] | None = None
    txt_token: str | None = None
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_error: str | None = None

    def touch(self) -> None:
        self.last_updated = datetime.now(UTC)
