"""Google Site Verification API client.

Handles TXT token retrieval and DNS_TXT verification flow.
"""

from __future__ import annotations

from typing import Any

from googleapiclient.errors import HttpError

from gsm.clients._google_errors import http_error_payload
from gsm.core.auth import OAuthDesktopAuth

__all__ = ["GoogleVerifyClient", "GoogleVerifyError"]


class GoogleVerifyError(RuntimeError):
    """Raised when Site Verification API returns a non-recoverable error."""


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
            raise GoogleVerifyError(f"failed to fetch TXT token for {domain}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleVerifyError(f"network error fetching TXT token for {domain}: {e}") from e

        token = response.get("token")
        if not token:
            raise GoogleVerifyError(f"empty token response for {domain}: {response}")
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
            payload = http_error_payload(e)
            if "already verified" in payload:
                return True
            raise GoogleVerifyError(f"verification failed for {domain}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleVerifyError(f"network error verifying {domain}: {e}") from e
