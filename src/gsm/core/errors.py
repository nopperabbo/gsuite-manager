"""Map raw exception messages to user-friendly explanations + fix hints.

Translates technical error strings (HTTP codes, API error codes, network
errors) into plain language the user can act on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FriendlyError:
    """User-facing error explanation + remediation hint."""

    summary: str
    hint: str | None = None

    def render(self) -> str:
        if self.hint:
            return f"{self.summary}\n  Cara fix: {self.hint}"
        return self.summary


def humanize(raw_error: str | Exception) -> FriendlyError:
    """Map a raw error message to a friendly explanation + hint."""
    text = str(raw_error).lower()

    if "invalid api token" in text or ("401" in text and "cloudflare" in text):
        return FriendlyError(
            "CF API Token tidak valid (401 Unauthorized).",
            "Buat token baru di https://dash.cloudflare.com/profile/api-tokens "
            "dan paste ulang ke .env (GSM_CF_API_TOKEN=...)",
        )
    if "403" in text and "cloudflare" in text:
        return FriendlyError(
            "CF API Token kurang permission (403 Forbidden).",
            "Pastikan token punya scope 'Zone:Edit' + 'DNS:Edit' "
            "untuk account yang benar.",
        )
    if "rate limit" in text or "429" in text:
        return FriendlyError(
            "Rate limit ke-trigger.",
            "Tambah delay di .env: GSM_DELAY_PER_DOMAIN_SEC=10 atau lebih, "
            "lalu retry.",
        )

    if "network error" in text or "timeout" in text or "connection" in text:
        return FriendlyError(
            "Koneksi internet bermasalah ke server.",
            "Cek koneksi internet, lalu retry. Kalo sering, "
            "naikin GSM_DNS_CHECK_TIMEOUT_SEC di .env.",
        )

    if "oauth client file not found" in text:
        return FriendlyError(
            "File OAuth Google (credentials.json) gak ketemu.",
            "Download file OAuth Desktop App dari Google Cloud Console "
            "(lihat docs/SETUP_GOOGLE_OAUTH.md), simpen sebagai credentials.json "
            "di folder project.",
        )
    if "scope" in text and ("invalid" in text or "missing" in text):
        return FriendlyError(
            "OAuth scope salah atau kurang permission.",
            "Hapus token.json (re-auth), pastikan akun Google yang login "
            "punya akses Workspace Admin.",
        )
    if "refresh" in text and "token" in text and ("expired" in text or "revoked" in text):
        return FriendlyError(
            "OAuth refresh token expired atau di-revoke.",
            "Hapus token.json, jalankan ulang command - browser akan minta login lagi.",
        )

    if "domain" in text and ("not found" in text or "does not exist" in text):
        return FriendlyError(
            "Domain belum terdaftar di Workspace.",
            "Run: gsm domains add <domain> dulu sebelum bikin user di domain itu.",
        )
    if "duplicate" in text or "already exists" in text or "409" in text:
        return FriendlyError(
            "Sudah ada (duplikat) - umumnya safe, di-skip.",
            None,
        )
    if "verification token could not be found" in text or (
        "txt" in text and "not found" in text
    ):
        return FriendlyError(
            "TXT record buat verifikasi belum ke-detect Google "
            "(DNS belum sepenuhnya propagasi).",
            "Tunggu 2-5 menit, lalu run: gsm domains verify --only-pending",
        )
    if "already verified" in text:
        return FriendlyError(
            "Domain sudah pernah di-verify sebelumnya.",
            None,
        )

    if "password" in text and ("weak" in text or "policy" in text):
        return FriendlyError(
            "Password gak memenuhi policy Google Workspace.",
            "Pakai password 8+ karakter dengan campuran huruf, angka, simbol.",
        )

    if "field required" in text or "validation error" in text:
        return FriendlyError(
            "Settingan di .env belum lengkap atau salah format.",
            "Run: gsm doctor untuk lihat field mana yang missing/salah.",
        )

    return FriendlyError(str(raw_error).split("\n")[0][:200])
