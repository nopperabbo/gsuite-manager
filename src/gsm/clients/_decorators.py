"""Decorators for Google API client methods.

Eliminates repetitive try/except boilerplate across all API methods by
centralizing error handling, idempotency semantics, and logging.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

import structlog
from googleapiclient.errors import HttpError

from gsm.clients._google_errors import http_error_payload, is_duplicate_error

__all__ = ["google_api_call"]

_log = structlog.get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def google_api_call(
    action: str,
    *,
    duplicate_ok: bool = False,
    not_found_ok: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Wrap a Google API method with consistent error handling.

    Args:
        action: Human-readable description for error messages (e.g. "add domain").
        duplicate_ok: If True, treat 409/duplicate as success (return None).
        not_found_ok: If True, treat 404/not-found as success (return None).
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return fn(*args, **kwargs)
            except HttpError as e:
                if duplicate_ok and is_duplicate_error(e):
                    _log.debug("google_api_duplicate_ok", action=action)
                    return True  # type: ignore[return-value]
                if not_found_ok:
                    payload = http_error_payload(e)
                    if "not found" in payload:
                        _log.debug("google_api_not_found_ok", action=action)
                        return True  # type: ignore[return-value]
                from gsm.clients.google_admin import GoogleAdminError

                raise GoogleAdminError(f"failed to {action}: {e}") from e
            except (TimeoutError, OSError) as e:
                from gsm.clients.google_admin import GoogleAdminError

                raise GoogleAdminError(f"network error during {action}: {e}") from e

        return wrapper

    return decorator
