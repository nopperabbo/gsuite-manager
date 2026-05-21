"""Shared error-handling utilities for Google API clients.

Extracted from google_admin.py and google_verify.py to avoid duplication.
"""

from __future__ import annotations

import contextlib
from typing import Any

__all__ = ["http_error_payload", "is_duplicate_error"]


def http_error_payload(err: Any) -> str:
    """Extract a lowercase searchable string from HttpError (body + reason + repr).

    Google API errors often have the meaningful detail in the response body
    (bytes), not the str(e) repr. We concatenate everything we can read.
    """
    parts: list[str] = []
    content = getattr(err, "content", None)
    if isinstance(content, bytes | bytearray):
        with contextlib.suppress(UnicodeDecodeError, AttributeError):
            parts.append(content.decode("utf-8", errors="replace"))
    elif isinstance(content, str):
        parts.append(content)

    resp = getattr(err, "resp", None)
    if resp is not None:
        reason = getattr(resp, "reason", None)
        if isinstance(reason, str):
            parts.append(reason)

    parts.append(repr(err))
    return " ".join(parts).lower()


def is_duplicate_error(err: Any) -> bool:
    """Detect whether HttpError represents an already-exists / duplicate condition.

    Google's "already exists" errors come as HTTP 409 OR HTTP 400 with various
    body shapes ("already exists", "duplicate", "entityAlreadyExists"). The
    body is in `err.content` (bytes), not str(err), so we sniff both.
    """
    status = getattr(err, "status_code", None) or getattr(
        getattr(err, "resp", None), "status", None
    )
    payload = http_error_payload(err)
    return (
        status == 409
        or "already exists" in payload
        or "duplicate" in payload
        or "entityalreadyexists" in payload
    )
