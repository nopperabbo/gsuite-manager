"""Google Workspace Admin Directory API client.

Wraps `admin/directory_v1` for domain operations. Handles 409/duplicate
responses as success for idempotency. Retries transient errors (429, 5xx,
network timeouts) with exponential backoff.
"""

from __future__ import annotations

import time as _time
from typing import Any, cast

import structlog
from googleapiclient.errors import HttpError

from gsm.clients._google_errors import (
    http_error_payload,
    is_duplicate_error,
)
from gsm.core.auth import OAuthDesktopAuth

__all__ = ["GoogleAdminClient", "GoogleAdminError"]

_log = structlog.get_logger(__name__)

# Transient HTTP statuses safe to retry.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503})
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BACKOFF = (1.0, 2.0, 4.0)


class GoogleAdminError(RuntimeError):
    """Raised when Admin Directory API returns a non-recoverable error."""


class GoogleAdminClient:
    """Client for Google Admin SDK Directory API (domains + users).

    All API calls are retried up to 3 times on transient errors (429, 5xx,
    network timeouts) with exponential backoff.
    """

    _retry_backoff: tuple[float, ...] = _DEFAULT_BACKOFF

    def __init__(self, auth: OAuthDesktopAuth) -> None:
        self._auth = auth
        self._service: Any | None = None

    def _admin(self) -> Any:
        if self._service is None:
            self._service = self._auth.build_admin_service()
        return self._service

    def _exec(self, request: Any) -> Any:
        """Execute a Google API request with retry on transient errors.

        Retries on HttpError 429/500/502/503 and network errors (TimeoutError,
        OSError). Non-retryable errors propagate immediately.
        """
        for attempt in range(_DEFAULT_MAX_ATTEMPTS):
            try:
                return request.execute()
            except HttpError as e:
                status = getattr(getattr(e, "resp", None), "status", None)
                if status not in _RETRYABLE_STATUSES or attempt >= _DEFAULT_MAX_ATTEMPTS - 1:
                    raise
                delay = self._retry_backoff[attempt]
                _log.warning(
                    "google_api_retry",
                    attempt=attempt + 1,
                    status=status,
                    delay=delay,
                )
                _time.sleep(delay)
            except (TimeoutError, OSError) as e:
                if attempt >= _DEFAULT_MAX_ATTEMPTS - 1:
                    raise
                delay = self._retry_backoff[attempt]
                _log.warning(
                    "google_api_retry",
                    attempt=attempt + 1,
                    error=str(e),
                    delay=delay,
                )
                _time.sleep(delay)
        # Unreachable, but satisfies type checker
        msg = "retry loop exited unexpectedly"
        raise RuntimeError(msg)

    def add_domain(self, domain: str) -> bool:
        """Add domain to Workspace. Treats already-exists as success.

        Returns True if domain is registered (newly added or already there).
        """
        try:
            self._exec(
                self._admin().domains().insert(
                    customer="my_customer",
                    body={"domainName": domain},
                )
            )
            return True
        except HttpError as e:
            if is_duplicate_error(e):
                return True
            raise GoogleAdminError(
                f"failed to add domain {domain}: {e}"
            ) from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(
                f"network error adding domain {domain}: {e}"
            ) from e

    def create_user(
        self,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        change_password_at_next_login: bool = False,
    ) -> bool:
        """Create a Workspace user. Treats already-exists as success.

        Returns True if user is registered (newly created or already there).
        """
        body = {
            "primaryEmail": email,
            "name": {
                "givenName": first_name,
                "familyName": last_name,
            },
            "password": password,
            "changePasswordAtNextLogin": change_password_at_next_login,
        }
        try:
            self._exec(self._admin().users().insert(body=body))
            return True
        except HttpError as e:
            if is_duplicate_error(e):
                return True
            raise GoogleAdminError(
                f"failed to create user {email}: {e}"
            ) from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(
                f"network error creating user {email}: {e}"
            ) from e

    def list_domains(self) -> list[dict[str, Any]]:
        """List all domains registered to the Workspace customer."""
        try:
            resp = self._exec(
                self._admin()
                .domains()
                .list(customer="my_customer")
            )
            return cast(list[dict[str, Any]], resp.get("domains", []))
        except HttpError as e:
            raise GoogleAdminError(f"failed to list domains: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error listing domains: {e}") from e

    def update_password(
        self, *, email: str, password: str, change_at_next_login: bool = False
    ) -> bool:
        """Update a user's password. Returns True on success."""
        try:
            self._exec(self._admin().users().update(
                userKey=email,
                body={
                    "password": password,
                    "changePasswordAtNextLogin": change_at_next_login,
                },
            ))
            return True
        except HttpError as e:
            raise GoogleAdminError(
                f"failed to reset password for {email}: {e}"
            ) from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(
                f"network error resetting password for {email}: {e}"
            ) from e

    def suspend_user(self, email: str) -> bool:
        """Suspend a user (block login). Idempotent."""
        try:
            self._exec(self._admin().users().update(
                userKey=email, body={"suspended": True}
            ))
            return True
        except HttpError as e:
            raise GoogleAdminError(f"failed to suspend {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(
                f"network error suspending {email}: {e}"
            ) from e

    def unsuspend_user(self, email: str) -> bool:
        """Unsuspend a user (re-enable login). Idempotent."""
        try:
            self._exec(self._admin().users().update(
                userKey=email, body={"suspended": False}
            ))
            return True
        except HttpError as e:
            raise GoogleAdminError(f"failed to unsuspend {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(
                f"network error unsuspending {email}: {e}"
            ) from e

    def list_users(self, domain: str | None = None) -> list[dict[str, Any]]:
        """List users. Optionally filter by domain."""
        try:
            kwargs: dict[str, Any] = {"customer": "my_customer", "maxResults": 500}
            if domain:
                kwargs["domain"] = domain
            users: list[dict[str, Any]] = []
            req = self._admin().users().list(**kwargs)
            while req is not None:
                resp = self._exec(req)
                users.extend(resp.get("users") or [])
                req = self._admin().users().list_next(req, resp)
            return users
        except HttpError as e:
            raise GoogleAdminError(f"failed to list users: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error listing users: {e}") from e

    def move_user_to_ou(self, email: str, org_unit_path: str) -> bool:
        """Move user to an Organizational Unit. Creates OU path if needed."""
        try:
            self._exec(self._admin().users().update(
                userKey=email, body={"orgUnitPath": org_unit_path}
            ))
            return True
        except HttpError as e:
            raise GoogleAdminError(
                f"failed to move {email} to OU '{org_unit_path}': {e}"
            ) from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(
                f"network error moving {email}: {e}"
            ) from e

    def delete_user(self, email: str) -> bool:
        """Delete a user permanently (30-day recovery window in Google)."""
        try:
            self._exec(self._admin().users().delete(userKey=email))
            return True
        except HttpError as e:
            payload = http_error_payload(e)
            if "not found" in payload:
                return True
            raise GoogleAdminError(f"failed to delete {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error deleting {email}: {e}") from e

    def add_alias(self, email: str, alias: str) -> bool:
        """Add email alias to a user."""
        try:
            self._exec(self._admin().users().aliases().insert(
                userKey=email, body={"alias": alias}
            ))
            return True
        except HttpError as e:
            payload = http_error_payload(e)
            if "duplicate" in payload or "already exists" in payload:
                return True
            raise GoogleAdminError(f"failed to add alias {alias} to {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error adding alias: {e}") from e

    def list_aliases(self, email: str) -> list[str]:
        """List all aliases for a user."""
        try:
            resp = self._exec(self._admin().users().aliases().list(userKey=email))
            aliases = resp.get("aliases", [])
            return [a.get("alias", "") for a in aliases if a.get("alias")]
        except HttpError as e:
            raise GoogleAdminError(f"failed to list aliases for {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error listing aliases: {e}") from e

    def remove_alias(self, email: str, alias: str) -> bool:
        """Remove email alias from a user."""
        try:
            self._exec(self._admin().users().aliases().delete(userKey=email, alias=alias))
            return True
        except HttpError as e:
            payload = http_error_payload(e)
            if "not found" in payload:
                return True
            raise GoogleAdminError(f"failed to remove alias {alias}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error removing alias: {e}") from e

    def assign_license(self, email: str, sku_id: str, product_id: str) -> bool:
        """Assign a license to a user via Licensing API."""
        try:
            from googleapiclient.discovery import build as _build
            licensing = _build("licensing", "v1", credentials=self._auth.get_credentials())
            self._exec(licensing.licenseAssignments().insert(
                productId=product_id,
                skuId=sku_id,
                body={"userId": email},
            ))
            return True
        except HttpError as e:
            payload = http_error_payload(e)
            if "duplicate" in payload or "already" in payload:
                return True
            raise GoogleAdminError(f"failed to assign license to {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error assigning license: {e}") from e

    def create_group(self, email: str, name: str | None = None, description: str = "") -> bool:
        """Create a Google Group (mailing list). Idempotent."""
        try:
            body: dict[str, Any] = {"email": email}
            if name:
                body["name"] = name
            if description:
                body["description"] = description
            self._exec(self._admin().groups().insert(body=body))
            return True
        except HttpError as e:
            if is_duplicate_error(e):
                return True
            raise GoogleAdminError(f"failed to create group {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error creating group: {e}") from e

    def list_groups(self, domain: str | None = None) -> list[dict[str, Any]]:
        """List groups, optionally filtered by domain."""
        try:
            kwargs: dict[str, Any] = {"customer": "my_customer", "maxResults": 200}
            if domain:
                kwargs["domain"] = domain
            groups: list[dict[str, Any]] = []
            req = self._admin().groups().list(**kwargs)
            while req is not None:
                resp = self._exec(req)
                groups.extend(resp.get("groups") or [])
                req = self._admin().groups().list_next(req, resp)
            return groups
        except HttpError as e:
            raise GoogleAdminError(f"failed to list groups: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error listing groups: {e}") from e

    def add_group_member(self, group_email: str, member_email: str, role: str = "MEMBER") -> bool:
        """Add member to a group. Idempotent."""
        try:
            self._exec(self._admin().members().insert(
                groupKey=group_email,
                body={"email": member_email, "role": role},
            ))
            return True
        except HttpError as e:
            if is_duplicate_error(e):
                return True
            raise GoogleAdminError(f"failed to add {member_email} to {group_email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error adding member: {e}") from e

    def remove_group_member(self, group_email: str, member_email: str) -> bool:
        """Remove member from a group."""
        try:
            self._exec(self._admin().members().delete(groupKey=group_email, memberKey=member_email))
            return True
        except HttpError as e:
            payload = http_error_payload(e)
            if "not found" in payload:
                return True
            raise GoogleAdminError(f"failed to remove {member_email} from {group_email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error removing member: {e}") from e

    def list_group_members(self, group_email: str) -> list[dict[str, Any]]:
        """List members of a group."""
        try:
            members: list[dict[str, Any]] = []
            req = self._admin().members().list(groupKey=group_email)
            while req is not None:
                resp = self._exec(req)
                members.extend(resp.get("members") or [])
                req = self._admin().members().list_next(req, resp)
            return members
        except HttpError as e:
            raise GoogleAdminError(f"failed to list members of {group_email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error listing members: {e}") from e

    def update_user(self, email: str, **fields: Any) -> bool:
        """Update user fields (name, phone, department, title, etc)."""
        try:
            body: dict[str, Any] = {}
            if "first_name" in fields or "last_name" in fields:
                body["name"] = {}
                if "first_name" in fields:
                    body["name"]["givenName"] = fields["first_name"]
                if "last_name" in fields:
                    body["name"]["familyName"] = fields["last_name"]
            for key in ("department", "title", "phone"):
                if key in fields:
                    if key == "phone":
                        body["phones"] = [{"value": fields[key], "type": "work", "primary": True}]
                    else:
                        body["organizations"] = [
                            {**body.get("organizations", [{}])[0], key: fields[key]}
                        ]
            if not body:
                return False
            self._exec(self._admin().users().update(userKey=email, body=body))
            return True
        except HttpError as e:
            raise GoogleAdminError(f"failed to update {email}: {e}") from e
        except (TimeoutError, OSError) as e:
            raise GoogleAdminError(f"network error updating {email}: {e}") from e

