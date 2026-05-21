"""Cloudflare API client - sync requests, idempotent operations.

Ports legacy patterns from gsuite_cloudflare_bot.py:
- Zone create: handle code 1061 (already exists) -> GET zone by name
- DNS record insert: treat code 81057/81058 (already exists) as success
- Bearer token auth, JSON content
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from gsm.core.config import Settings

__all__ = ["CF_BASE_URL", "CloudflareClient", "CloudflareError", "ZoneInfo"]

CF_BASE_URL = "https://api.cloudflare.com/client/v4"
DEFAULT_TIMEOUT = 15


class CloudflareError(RuntimeError):
    """Raised when Cloudflare API returns a non-recoverable error."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ZoneInfo:
    """Result of a zone lookup or creation.

    `created` indicates whether the zone was newly created during this call.
    """

    zone_id: str
    name: str
    nameservers: list[str]
    created: bool


class CloudflareClient:
    """Thin sync wrapper around Cloudflare v4 API.

    Methods are idempotent: existing zones / records are treated as success
    so workflows can be safely re-run.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token = settings.cf_api_token.get_secret_value()
        self._account_id = settings.cf_account_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            }
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import time as _time

        max_attempts = 3
        backoff = [1.0, 3.0, 5.0]
        last_exc: Exception | None = None

        for attempt in range(max_attempts):
            try:
                resp = self._session.request(
                    method, url, json=json, params=params, timeout=DEFAULT_TIMEOUT
                )
                if resp.status_code in (502, 503, 429) and attempt < max_attempts - 1:
                    _time.sleep(backoff[attempt])
                    continue
                try:
                    return resp.json()  # type: ignore[no-any-return]
                except ValueError as e:
                    raise CloudflareError(
                        f"non-JSON response from Cloudflare (status={resp.status_code})"
                    ) from e
            except requests.RequestException as e:
                last_exc = e
                if attempt < max_attempts - 1:
                    _time.sleep(backoff[attempt])
                    continue
                raise CloudflareError(
                    f"network error talking to Cloudflare ({method} {url}): {e}"
                ) from e

        raise CloudflareError(
            f"failed after {max_attempts} attempts ({method} {url}): {last_exc}"
        )

    def ensure_zone(self, domain: str) -> ZoneInfo:
        """Create zone or fetch existing one. Returns ZoneInfo with nameservers populated.

        Raises CloudflareError on hard failures (auth, network, unexpected codes).
        """
        created = self._try_create_zone(domain)
        zone = self._get_zone_by_name(domain)
        if zone is None:
            raise CloudflareError(f"zone not found after ensure: {domain}")
        return ZoneInfo(
            zone_id=zone["id"],
            name=zone["name"],
            nameservers=list(zone.get("name_servers", [])),
            created=created,
        )

    def get_zone_by_name(self, domain: str) -> ZoneInfo | None:
        """Fetch zone info by name. Returns None if zone does not exist."""
        zone = self._get_zone_by_name(domain)
        if zone is None:
            return None
        return ZoneInfo(
            zone_id=zone["id"],
            name=zone["name"],
            nameservers=list(zone.get("name_servers", [])),
            created=False,
        )

    def list_zones(self) -> list[ZoneInfo]:
        """List all zones in the configured CF account (paginated, fetches all)."""
        all_zones: list[ZoneInfo] = []
        page = 1
        while True:
            data = self._request(
                "GET",
                f"{CF_BASE_URL}/zones",
                params={
                    "account.id": self._account_id,
                    "per_page": 50,
                    "page": page,
                },
            )
            if not data.get("success"):
                msg = "; ".join(
                    e.get("message", "?") for e in data.get("errors", [])
                )
                raise CloudflareError(f"failed to list zones: {msg}")
            for zone in data.get("result", []):
                all_zones.append(
                    ZoneInfo(
                        zone_id=zone["id"],
                        name=zone["name"],
                        nameservers=list(zone.get("name_servers", [])),
                        created=False,
                    )
                )
            info = data.get("result_info", {})
            total_pages = info.get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1
        return all_zones

    def get_email_routing_status(self, zone_id: str) -> bool | None:
        """Return True if Email Routing enabled, False if disabled, None if unset."""
        try:
            data = self._request(
                "GET", f"{CF_BASE_URL}/zones/{zone_id}/email/routing"
            )
        except CloudflareError:
            return None
        if not data.get("success"):
            return None
        result = data.get("result") or {}
        if not isinstance(result, dict):
            return None
        return bool(result.get("enabled", False))

    def disable_email_routing(self, zone_id: str) -> bool:
        """Disable Cloudflare Email Routing on a zone (idempotent).

        Returns True if disabled (or was already disabled), raises on hard failure.
        Required before injecting custom MX records (Workspace integration).
        """
        data = self._request(
            "POST", f"{CF_BASE_URL}/zones/{zone_id}/email/routing/disable"
        )
        if data.get("success"):
            return True
        for err in data.get("errors", []):
            msg = err.get("message", "").lower()
            if "not enabled" in msg or "already disabled" in msg or "unconfigured" in msg:
                return True
        msg = "; ".join(e.get("message", "?") for e in data.get("errors", []))
        raise CloudflareError(
            f"failed to disable email routing on zone {zone_id}: {msg}"
        )

    def upsert_dns_record(
        self,
        zone_id: str,
        *,
        record_type: str,
        name: str,
        content: str,
        priority: int | None = None,
        ttl: int = 1,
        proxied: bool = False,
    ) -> bool:
        """Create DNS record, treating "already exists" responses (81057/81058) as success.

        Returns True when record exists in CF after the call.
        """
        url = f"{CF_BASE_URL}/zones/{zone_id}/dns_records"
        payload: dict[str, Any] = {
            "type": record_type,
            "name": name,
            "content": content,
            "ttl": ttl,
            "proxied": proxied,
        }
        if priority is not None:
            payload["priority"] = priority

        data = self._request("POST", url, json=payload)

        if data.get("success"):
            return True

        for err in data.get("errors", []):
            code = err.get("code", 0)
            msg = err.get("message", "").lower()
            if code in (81057, 81058) or "already exists" in msg:
                return True

        msg = "; ".join(e.get("message", "Unknown") for e in data.get("errors", []))
        raise CloudflareError(
            f"failed to create DNS {record_type} {name}={content}: {msg}",
            code=data.get("errors", [{}])[0].get("code"),
        )

    def _try_create_zone(self, domain: str) -> bool:
        """Attempt to create zone. Returns True if newly created, False if already existed."""
        url = f"{CF_BASE_URL}/zones"
        payload = {
            "name": domain,
            "account": {"id": self._account_id},
            "type": "full",
        }
        data = self._request("POST", url, json=payload)

        if data.get("success"):
            return True

        for err in data.get("errors", []):
            if err.get("code") == 1061:
                return False

        msg = "; ".join(e.get("message", "Unknown") for e in data.get("errors", []))
        raise CloudflareError(
            f"failed to create zone {domain}: {msg}",
            code=data.get("errors", [{}])[0].get("code"),
        )

    def _get_zone_by_name(self, domain: str) -> dict[str, Any] | None:
        url = f"{CF_BASE_URL}/zones"
        data = self._request("GET", url, params={"name": domain})
        if not data.get("success"):
            msg = "; ".join(
                e.get("message", "Unknown") for e in data.get("errors", [])
            )
            raise CloudflareError(f"failed to query zone {domain}: {msg}")
        results: list[dict[str, Any]] = data.get("result", [])
        if not results:
            return None
        return results[0]
