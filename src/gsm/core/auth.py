from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, ClassVar, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from gsm.core.config import Settings


class AuthError(RuntimeError):
    pass


class OAuthDesktopAuth:
    SCOPES: ClassVar[list[str]] = [
        "https://www.googleapis.com/auth/siteverification",
        "https://www.googleapis.com/auth/admin.directory.domain",
        "https://www.googleapis.com/auth/admin.directory.user",
    ]

    def __init__(self, settings: Settings) -> None:
        self._client_path: Path = settings.google_oauth_client_path
        self._token_path: Path = settings.google_oauth_token_path
        self._creds: Credentials | None = None
        self._lock = threading.Lock()

    def get_credentials(self) -> Credentials:
        with self._lock:
            if self._creds is not None and self._creds.valid:
                return self._creds
            self._creds = self._load_or_refresh()
            return self._creds

    def build_admin_service(self) -> Any:
        return build("admin", "directory_v1", credentials=self.get_credentials())

    def build_verify_service(self) -> Any:
        return build("siteVerification", "v1", credentials=self.get_credentials())

    def has_cached_token(self) -> bool:
        return self._token_path.exists()

    def _load_or_refresh(self) -> Credentials:
        creds = self._load_from_disk()

        if creds is not None and creds.valid:
            return creds

        if creds is not None and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())  # type: ignore[no-untyped-call]
                self._save_to_disk(creds)
                return creds
            except Exception:
                creds = None

        return self._run_browser_flow()

    def _load_from_disk(self) -> Credentials | None:
        if not self._token_path.exists():
            return None
        try:
            return cast(
                Credentials,
                Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                    str(self._token_path), self.SCOPES
                ),
            )
        except Exception:
            return None

    def _run_browser_flow(self) -> Credentials:
        if not self._client_path.exists():
            raise AuthError(
                f"OAuth client file not found: {self._client_path}. "
                "Place credentials.json or client_secret_*.json there, "
                "or set GSM_GOOGLE_OAUTH_CLIENT_PATH."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self._client_path), self.SCOPES
        )
        creds = cast(Credentials, flow.run_local_server(port=0))
        self._save_to_disk(creds)
        return creds

    def _save_to_disk(self, creds: Credentials) -> None:
        # Atomic write via tmp+rename to avoid corruption mid-write.
        # File mode 0o600 because token grants admin.directory.user scope.
        tmp = self._token_path.with_suffix(self._token_path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(creds.to_json())  # type: ignore[no-untyped-call]
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._token_path)


def detect_oauth_client_file(search_dir: Path) -> Path | None:
    candidate = search_dir / "credentials.json"
    if candidate.exists():
        return candidate
    for entry in search_dir.iterdir():
        if entry.is_file() and entry.name.startswith("client_secret_") and entry.suffix == ".json":
            return entry
    return None
