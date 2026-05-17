from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ResultKind(StrEnum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    FAILED = "failed"


class ItemResult(BaseModel):
    identifier: str
    kind: ResultKind
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success(cls, identifier: str, message: str = "ok", **details: Any) -> ItemResult:
        return cls(identifier=identifier, kind=ResultKind.SUCCESS, message=message, details=details)

    @classmethod
    def skipped(cls, identifier: str, message: str, **details: Any) -> ItemResult:
        return cls(identifier=identifier, kind=ResultKind.SKIPPED, message=message, details=details)

    @classmethod
    def partial(cls, identifier: str, message: str, **details: Any) -> ItemResult:
        return cls(identifier=identifier, kind=ResultKind.PARTIAL, message=message, details=details)

    @classmethod
    def failed(cls, identifier: str, message: str, **details: Any) -> ItemResult:
        return cls(kind=ResultKind.FAILED, identifier=identifier, message=message, details=details)
