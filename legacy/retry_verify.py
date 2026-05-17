#!/usr/bin/env python3
"""
Retry verifikasi domain yang gagal (DNS belum propagasi saat run utama).
Akan retry tiap domain sampai 5x dengan jeda 30 detik antar retry.
"""

import sys
import os
import time
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GOOGLE_OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/siteverification",
    "https://www.googleapis.com/auth/admin.directory.domain",
]

DOMAINS = [
    # Batch 1 - 8 domain (NS: norman + rosalie)
    "kamuu.tech", "dabon.tech", "kibee.tech", "vufen.tech",
    "fijoa.tech", "keboi.tech", "donwu.tech", "kogii.tech",
    # Batch 2 - 6 domain (NS: wren + yahir)
    "zonze.tech", "ricie.tech", "cucia.tech", "rekaa.tech",
    "majau.tech", "wugen.tech",
]

MAX_RETRIES = 3
RETRY_DELAY = 30


def log(status, message):
    prefix_map = {"ok": "[+]", "fail": "[-]", "info": "[*]"}
    prefix = prefix_map.get(status, "[?]")
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  {prefix} [{ts}] {message}", flush=True)


def detect_oauth_client_file():
    for filename in os.listdir(SCRIPT_DIR):
        if filename == "credentials.json":
            return os.path.join(SCRIPT_DIR, filename)
        if filename.startswith("client_secret_") and filename.endswith(".json"):
            return os.path.join(SCRIPT_DIR, filename)
    return None


def build_service():
    credentials = None
    if os.path.exists(GOOGLE_OAUTH_TOKEN_FILE):
        try:
            credentials = Credentials.from_authorized_user_file(
                GOOGLE_OAUTH_TOKEN_FILE, GOOGLE_SCOPES
            )
        except Exception:
            credentials = None

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            with open(GOOGLE_OAUTH_TOKEN_FILE, "w") as f:
                f.write(credentials.to_json())
            log("ok", "OAuth token refreshed.")
        except Exception:
            credentials = None

    if not credentials or not credentials.valid:
        oauth_file = detect_oauth_client_file()
        if not oauth_file:
            log("fail", "OAuth client file not found!")
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(oauth_file, GOOGLE_SCOPES)
        credentials = flow.run_local_server(port=0)
        with open(GOOGLE_OAUTH_TOKEN_FILE, "w") as f:
            f.write(credentials.to_json())

    return build("siteVerification", "v1", credentials=credentials)


def verify_domain(service, domain):
    try:
        response = service.webResource().insert(
            verificationMethod="DNS_TXT",
            body={"site": {"type": "INET_DOMAIN", "identifier": domain}},
        ).execute()
        site_id = response.get("id", "")
        if site_id:
            log("ok", f"'{domain}' BERHASIL DIVERIFIKASI! (id: {site_id})")
            return True
        log("ok", f"'{domain}' verifikasi response: {response}")
        return True
    except Exception as e:
        err_str = str(e)
        if "already verified" in err_str.lower():
            log("info", f"'{domain}' sudah terverifikasi sebelumnya (skip)")
            return True
        log("fail", f"Gagal verifikasi '{domain}': {err_str}")
        return False


def main():
    print("\n" + "=" * 60)
    print("  RETRY VERIFIKASI DOMAIN")
    print(f"  {len(DOMAINS)} domain | max {MAX_RETRIES} retry | delay {RETRY_DELAY}s")
    print("=" * 60 + "\n")

    service = build_service()
    log("ok", "Google Site Verification API client ready.\n")

    verified = []
    still_failed = list(DOMAINS)

    for attempt in range(1, MAX_RETRIES + 1):
        if not still_failed:
            break

        print(f"\n--- Attempt {attempt}/{MAX_RETRIES} ({len(still_failed)} domain tersisa) ---")

        newly_verified = []
        for domain in still_failed:
            if verify_domain(service, domain):
                newly_verified.append(domain)
            time.sleep(2)

        for d in newly_verified:
            still_failed.remove(d)
            verified.append(d)

        if still_failed and attempt < MAX_RETRIES:
            log("info", f"Masih gagal {len(still_failed)} domain. Tunggu {RETRY_DELAY}s sebelum retry...")
            time.sleep(RETRY_DELAY)

    print("\n" + "=" * 60)
    print("  HASIL RETRY VERIFIKASI")
    print("=" * 60)
    print(f"  Berhasil : {len(verified)}")
    for d in verified:
        print(f"    ✅ {d}")
    print(f"  Gagal    : {len(still_failed)}")
    for d in still_failed:
        print(f"    ❌ {d}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
