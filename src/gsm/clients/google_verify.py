"""Google Site Verification API client.

Handles TXT token retrieval and DNS_TXT verification flow.
"""

from __future__ import annotations

import contextlib
from typing import Any

from googleapiclient.errors import HttpError

from gsm.core.auth import OAuthDesktopAuth


class GoogleVerifyError(RuntimeError):
    """Raised when Site Verification API returns a non-recoverable error."""


def _http_error_payload(err: Any) -> str:
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


class GoogleVerifyClient:
    """Client for Google Site Verification API."""

    def __init__(self, auth: OAuthDesktopAuth) -> None:
        self._auth = auth
        self._service: Any | None = None

    def _verify(self) -> Any:
        if self._service is None:
            self._service = self._auth.build_verify_service()
        return self._service

    def get_dns_txt_token(self, domain: str) -> str:
        """Fetch the unique DNS_TXT verification token for a domain.

        Raises GoogleVerifyError if API returns no token or an error.
        """
        try:
            response = (
                self._verify()
                .webResource()
                .getToken(
                    body={
                        "site": {"type": "INET_DOMAIN", "identifier": domain},
                        "verificationMethod": "DNS_TXT",
                    }
                )
                .execute()
            )
        except HttpError as e:
            raise GoogleVerifyError(
                f"failed to fetch TXT token for {domain}: {e}"
            ) from e
        except (TimeoutError, OSError) as e:
            raise GoogleVerifyError(
                f"network error fetching TXT token for {domain}: {e}"
            ) from e

        token = response.get("token")
        if not token:
            raise GoogleVerifyError(
                f"empty token response for {domain}: {response}"
            )
        return str(token)

    def verify_domain(self, domain: str) -> bool:
        """Tell Google to verify the domain via DNS_TXT.

        Returns True on success or already-verified. Raises GoogleVerifyError
        if Google reports the token cannot be found (DNS not propagated yet)
        or any other error.
        """
        try:
            self._verify().webResource().insert(
                verificationMethod="DNS_TXT",
                body={"site": {"type": "INET_DOMAIN", "identifier": domain}},
            ).execute()
            return True
        except HttpError as e:
            payload = _http_error_payload(e)
            if "already verified" in payload:
                return True
            raise GoogleVerifyError(
                f"verification failed for {domain}: {e}"
            ) from e
        except (TimeoutError, OSError) as e:
            raise GoogleVerifyError(
                f"network error verifying {domain}: {e}"
            ) from e
