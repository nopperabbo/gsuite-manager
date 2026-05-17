#!/usr/bin/env python3
"""
=============================================================================
  Google Workspace Domain Adder + Cloudflare DNS Automation
=============================================================================
  Alur:
    1. Baca domain dari domains.txt
    2. Tambahkan domain ke G Suite via GAM (subprocess)
    3. Ambil TXT verification token via Google Site Verification API
    4. Tambahkan domain ke Cloudflare (Create Zone API)
    5. Ambil & tampilkan Nameserver dari Cloudflare
    6. Inject DNS Record: 5 MX Google Workspace + TXT Verifikasi (dynamic)
    7. Sleep 3 detik per domain (anti rate-limit)
    8. Log rapi di terminal + simpan hasil ke result_log.txt

  Dependensi:
    pip install requests google-auth google-auth-oauthlib google-api-python-client
    GAM sudah terinstall & terkonfigurasi (https://github.com/GAM-team/GAM)

  Setup Google OAuth Desktop App:
    1. Buka https://console.cloud.google.com
    2. Enable "Google Site Verification API"
    3. Buat OAuth Client ID tipe "Desktop app"
    4. Download file JSON OAuth client ke folder ini
    5. Saat run pertama, login via browser menggunakan akun admin Google Workspace
    6. Script akan simpan token login ke token.json untuk run berikutnya
=============================================================================
"""

import requests
import time
import sys
import os
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# ===========================================================================
#  KONFIGURASI
# ===========================================================================

CF_API_TOKEN = "Qh1dr2J1GydCiiIDerH-vGf69k6XQDSToN4MvOIh"
CF_ACCOUNT_ID = "0061a056f8cbc860fb9ec99bd41a0ccc"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# File OAuth client JSON (Desktop App). Jika None, script akan auto-detect
# file bernama credentials.json atau client_secret_*.json di folder ini.
GOOGLE_OAUTH_CLIENT_FILE = None

# Token hasil login browser pertama akan disimpan di file ini.
GOOGLE_OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")

DOMAINS_FILE = os.path.join(SCRIPT_DIR, "domains.txt")
LOG_FILE = os.path.join(SCRIPT_DIR, "result_log.txt")

DELAY_PER_DOMAIN = 3


# ===========================================================================
#  KONSTANTA
# ===========================================================================

CF_BASE_URL = "https://api.cloudflare.com/client/v4"

GOOGLE_MX_RECORDS = [
    {"name": "@", "content": "ASPMX.L.GOOGLE.COM",      "priority": 1},
    {"name": "@", "content": "ALT1.ASPMX.L.GOOGLE.COM",  "priority": 5},
    {"name": "@", "content": "ALT2.ASPMX.L.GOOGLE.COM",  "priority": 5},
    {"name": "@", "content": "ALT3.ASPMX.L.GOOGLE.COM",  "priority": 10},
    {"name": "@", "content": "ALT4.ASPMX.L.GOOGLE.COM",  "priority": 10},
]

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/siteverification",
    "https://www.googleapis.com/auth/admin.directory.domain",
]


# ===========================================================================
#  GOOGLE SITE VERIFICATION API CLIENT (OAuth Desktop App)
# ===========================================================================

def detect_oauth_client_file() -> str | None:
    if GOOGLE_OAUTH_CLIENT_FILE:
        if os.path.exists(GOOGLE_OAUTH_CLIENT_FILE):
            return GOOGLE_OAUTH_CLIENT_FILE

        log("fail", f"OAuth client file tidak ditemukan: {GOOGLE_OAUTH_CLIENT_FILE}")
        return None

    candidate_names = ["credentials.json"]
    for candidate in candidate_names:
        candidate_path = os.path.join(SCRIPT_DIR, candidate)
        if os.path.exists(candidate_path):
            return candidate_path

    for filename in os.listdir(SCRIPT_DIR):
        if filename.startswith("client_secret_") and filename.endswith(".json"):
            return os.path.join(SCRIPT_DIR, filename)

    return None


def build_verification_service():
    """
    Buat Google Site Verification API client menggunakan OAuth2 Desktop App.
    Run pertama akan buka browser untuk login, lalu token disimpan agar
    run berikutnya tidak perlu login lagi.
    """
    oauth_client_file = detect_oauth_client_file()
    if not oauth_client_file:
        log("fail", "File OAuth client JSON tidak ditemukan di folder script.")
        log("fail", "Taruh file `credentials.json` atau `client_secret_*.json` di folder ini.")
        sys.exit(1)

    credentials = None

    if os.path.exists(GOOGLE_OAUTH_TOKEN_FILE):
        try:
            credentials = Credentials.from_authorized_user_file(
                GOOGLE_OAUTH_TOKEN_FILE,
                GOOGLE_SCOPES,
            )
        except Exception as e:
            log("info", f"token.json tidak valid / tidak bisa dibaca, login ulang akan diminta: {e}")
            credentials = None

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            with open(GOOGLE_OAUTH_TOKEN_FILE, "w", encoding="utf-8") as token_file:
                token_file.write(credentials.to_json())
            log("ok", "OAuth token berhasil di-refresh.")
        except Exception as e:
            log("info", f"Refresh token gagal, login browser akan diminta ulang: {e}")
            credentials = None

    if not credentials or not credentials.valid:
        log("info", f"Menjalankan login browser Google menggunakan file OAuth: {os.path.basename(oauth_client_file)}")
        flow = InstalledAppFlow.from_client_secrets_file(
            oauth_client_file,
            GOOGLE_SCOPES,
        )
        credentials = flow.run_local_server(port=0)

        with open(GOOGLE_OAUTH_TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(credentials.to_json())

        log("ok", f"OAuth token tersimpan di: {GOOGLE_OAUTH_TOKEN_FILE}")

    verification_svc = build("siteVerification", "v1", credentials=credentials)
    admin_svc = build("admin", "directory_v1", credentials=credentials)
    return verification_svc, admin_svc


def get_verification_txt_token(service, domain: str) -> str | None:
    """
    Hit Google Site Verification API endpoint getToken untuk mendapatkan
    TXT verification string unik per domain.

    API: POST https://www.googleapis.com/siteVerification/v1/token
    Body: { site: { type: "INET_DOMAIN", identifier: domain }, verificationMethod: "DNS_TXT" }
    Response: { method: "DNS_TXT", token: "google-site-verification=xxxxx" }
    """
    try:
        response = service.webResource().getToken(body={
            "site": {
                "type": "INET_DOMAIN",
                "identifier": domain,
            },
            "verificationMethod": "DNS_TXT",
        }).execute()

        token = response.get("token")
        if token:
            log("ok", f"TXT verification token untuk '{domain}': {token}")
            return token

        log("fail", f"Response getToken kosong untuk '{domain}': {response}")
        return None

    except Exception as e:
        log("fail", f"Gagal ambil TXT token untuk '{domain}': {e}")
        return None


def verify_domain(service, domain: str) -> bool:
    """
    Hit Google Site Verification API endpoint insert (verify) untuk
    memverifikasi domain setelah DNS TXT record sudah di-inject.

    API: POST https://www.googleapis.com/siteVerification/v1/webResource
    Params: verificationMethod=DNS_TXT
    Body: { site: { type: "INET_DOMAIN", identifier: domain } }
    """
    try:
        response = service.webResource().insert(
            verificationMethod="DNS_TXT",
            body={
                "site": {
                    "type": "INET_DOMAIN",
                    "identifier": domain,
                },
            },
        ).execute()

        site_id = response.get("id", "")
        if site_id:
            log("ok", f"Domain '{domain}' BERHASIL DIVERIFIKASI! (id: {site_id})")
            return True

        log("ok", f"Domain '{domain}' verifikasi response: {response}")
        return True

    except Exception as e:
        err_str = str(e)
        if "already verified" in err_str.lower():
            log("info", f"Domain '{domain}' sudah terverifikasi sebelumnya (skip)")
            return True
        log("fail", f"Gagal verifikasi domain '{domain}': {err_str}")
        return False


# ===========================================================================
#  HELPER FUNCTIONS
# ===========================================================================

def log(status: str, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = "[+]" if status == "ok" else "[-]" if status == "fail" else "[*]"
    line = f"{timestamp} {prefix} {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def cf_headers() -> dict:
    return {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }


def load_domains(filepath: str) -> list[str]:
    if not os.path.exists(filepath):
        log("fail", f"File tidak ditemukan: {filepath}")
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        domains = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not domains:
        log("fail", "File domains.txt kosong atau tidak ada domain valid.")
        sys.exit(1)

    return domains


# ===========================================================================
#  STEP 1: Tambah Domain ke Google Workspace via GAM
# ===========================================================================

def add_domain_to_gsuite(admin_service, domain: str) -> bool:
    """Tambah domain ke Google Workspace via Admin SDK Directory API."""
    try:
        body = {"domainName": domain}
        admin_service.domains().insert(customer="my_customer", body=body).execute()
        log("ok", f"Sukses add domain '{domain}' ke G Suite")
        return True
    except Exception as e:
        err_str = str(e)
        if "409" in err_str or "already exists" in err_str.lower() or "duplicate" in err_str.lower():
            log("info", f"Domain '{domain}' sudah ada di G Suite (skip)")
            return True
        log("fail", f"Gagal add domain '{domain}' ke G Suite: {err_str}")
        return False


# ===========================================================================
#  STEP 2: Tambah Domain (Zone) ke Cloudflare
# ===========================================================================

def create_cloudflare_zone(domain: str) -> str | None:
    url = f"{CF_BASE_URL}/zones"
    payload = {
        "name": domain,
        "account": {"id": CF_ACCOUNT_ID},
        "type": "full",
    }

    try:
        resp = requests.post(url, json=payload, headers=cf_headers(), timeout=15)
        data = resp.json()

        if data.get("success"):
            zone_id = data["result"]["id"]
            log("ok", f"Sukses add Zone Cloudflare untuk '{domain}' (zone_id: {zone_id})")
            return zone_id

        errors = data.get("errors", [])
        for err in errors:
            if err.get("code") == 1061:
                log("info", f"Zone '{domain}' sudah ada di Cloudflare, mencoba ambil zone_id...")
                return get_existing_zone_id(domain)

        error_msg = "; ".join(e.get("message", "Unknown") for e in errors)
        log("fail", f"Gagal create Zone CF untuk '{domain}': {error_msg}")
        return None

    except requests.exceptions.Timeout:
        log("fail", f"Timeout hit API Cloudflare untuk '{domain}'")
        return None
    except requests.exceptions.RequestException as e:
        log("fail", f"Error hit API Cloudflare untuk '{domain}': {e}")
        return None


def get_existing_zone_id(domain: str) -> str | None:
    url = f"{CF_BASE_URL}/zones"
    params = {"name": domain}

    try:
        resp = requests.get(url, params=params, headers=cf_headers(), timeout=15)
        data = resp.json()

        if data.get("success") and data["result"]:
            zone_id = data["result"][0]["id"]
            log("ok", f"Ditemukan zone_id existing untuk '{domain}': {zone_id}")
            return zone_id

        log("fail", f"Tidak bisa ambil zone_id existing untuk '{domain}'")
        return None

    except requests.exceptions.RequestException as e:
        log("fail", f"Error ambil zone_id untuk '{domain}': {e}")
        return None


# ===========================================================================
#  STEP 3: Ambil Nameserver dari Cloudflare
# ===========================================================================

def get_cloudflare_nameservers(zone_id: str, domain: str) -> list[str]:
    url = f"{CF_BASE_URL}/zones/{zone_id}"

    try:
        resp = requests.get(url, headers=cf_headers(), timeout=15)
        data = resp.json()

        if data.get("success"):
            nameservers = data["result"].get("name_servers", [])
            if nameservers:
                log("ok", f"Nameserver CF untuk '{domain}':")
                for ns in nameservers:
                    print(f"           NS -> {ns}")
                return nameservers

            log("info", f"Nameserver belum tersedia untuk '{domain}'")
            return []

        log("fail", f"Gagal ambil nameserver untuk '{domain}'")
        return []

    except requests.exceptions.RequestException as e:
        log("fail", f"Error ambil nameserver untuk '{domain}': {e}")
        return []


# ===========================================================================
#  STEP 4: Inject DNS Records ke Cloudflare
# ===========================================================================

def add_dns_record(zone_id: str, domain: str, record_type: str,
                   name: str, content: str, priority: int | None = None,
                   ttl: int = 1) -> bool:
    url = f"{CF_BASE_URL}/zones/{zone_id}/dns_records"

    record_name = domain if name == "@" else f"{name}.{domain}"

    payload: dict = {
        "type": record_type,
        "name": record_name,
        "content": content,
        "ttl": ttl,
    }

    if priority is not None:
        payload["priority"] = priority

    if record_type in ("MX", "TXT"):
        payload["proxied"] = False

    try:
        resp = requests.post(url, json=payload, headers=cf_headers(), timeout=15)
        data = resp.json()

        if data.get("success"):
            extra = f" (priority: {priority})" if priority is not None else ""
            log("ok", f"  DNS {record_type} -> {content}{extra}")
            return True

        errors = data.get("errors", [])
        for err in errors:
            err_code = err.get("code", 0)
            err_msg = err.get("message", "").lower()
            if err_code in (81057, 81058) or "already exists" in err_msg:
                log("info", f"  DNS {record_type} -> {content} (sudah ada, skip)")
                return True

        error_msg = "; ".join(e.get("message", "Unknown") for e in errors)
        log("fail", f"  Gagal DNS {record_type} -> {content}: {error_msg}")
        return False

    except requests.exceptions.RequestException as e:
        log("fail", f"  Error DNS {record_type} -> {content}: {e}")
        return False


def inject_google_workspace_dns(zone_id: str, domain: str, txt_token: str | None) -> None:
    log("info", f"Inject DNS records untuk '{domain}'...")

    for mx in GOOGLE_MX_RECORDS:
        add_dns_record(
            zone_id=zone_id,
            domain=domain,
            record_type="MX",
            name=mx["name"],
            content=mx["content"],
            priority=mx["priority"],
        )

    if txt_token:
        add_dns_record(
            zone_id=zone_id,
            domain=domain,
            record_type="TXT",
            name="@",
            content=txt_token,
        )
    else:
        log("info", f"TXT verification untuk '{domain}' dilewati karena token tidak tersedia.")


# ===========================================================================
#  MAIN
# ===========================================================================

def main() -> None:
    if "ISI_" in CF_API_TOKEN or "ISI_" in CF_ACCOUNT_ID:
        print("\n[!] ERROR: Kamu belum mengisi CF_API_TOKEN atau CF_ACCOUNT_ID!")
        sys.exit(1)

    domains = load_domains(DOMAINS_FILE)

    log("info", "Menginisialisasi Google API clients...")
    verification_service, admin_service = build_verification_service()
    log("ok", "Google API clients siap (Site Verification + Admin Directory).")

    print("=" * 65)
    print("  G Suite + Cloudflare Domain Automation (Dynamic TXT)")
    print(f"  Total domain: {len(domains)}")
    print(f"  Delay per domain: {DELAY_PER_DOMAIN} detik")
    print(f"  Waktu mulai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    print()

    stats = {
        "gsuite_ok": 0, "gsuite_fail": 0,
        "cf_ok": 0, "cf_fail": 0,
        "txt_ok": 0, "txt_fail": 0,
        "dns_ok": 0,
        "verify_ok": 0, "verify_fail": 0,
    }

    for idx, domain in enumerate(domains, start=1):
        print(f"\n{'─' * 55}")
        log("info", f"[{idx}/{len(domains)}] Memproses domain: {domain}")
        print(f"{'─' * 55}")

        # --- STEP 1: Add ke G Suite via Admin SDK ---
        if add_domain_to_gsuite(admin_service, domain):
            stats["gsuite_ok"] += 1
        else:
            stats["gsuite_fail"] += 1

        # --- STEP 2: Ambil TXT verification token dari Google API ---
        txt_token = get_verification_txt_token(verification_service, domain)
        if txt_token:
            stats["txt_ok"] += 1
        else:
            stats["txt_fail"] += 1
            log("fail", f"Skip DNS TXT inject untuk '{domain}' (token gagal diambil)")

        # --- STEP 3: Create Zone di Cloudflare ---
        zone_id = create_cloudflare_zone(domain)
        if zone_id:
            stats["cf_ok"] += 1

            # --- STEP 4: Ambil & tampilkan Nameserver ---
            get_cloudflare_nameservers(zone_id, domain)

            # --- STEP 5: Inject DNS Records (MX + TXT jika ada) ---
            inject_google_workspace_dns(
                zone_id=zone_id,
                domain=domain,
                txt_token=txt_token,
            )
            if txt_token:
                stats["dns_ok"] += 1

            # --- STEP 6: Verifikasi domain di Google ---
            if txt_token:
                if verify_domain(verification_service, domain):
                    stats["verify_ok"] += 1
                else:
                    stats["verify_fail"] += 1
            else:
                log("info", f"Skip verifikasi '{domain}' (TXT token tidak tersedia)")
                stats["verify_fail"] += 1
        else:
            stats["cf_fail"] += 1
            log("fail", f"Skip DNS inject untuk '{domain}' (zone gagal dibuat)")

        # --- Delay anti rate-limit ---
        if idx < len(domains):
            log("info", f"Menunggu {DELAY_PER_DOMAIN} detik (anti rate-limit)...")
            time.sleep(DELAY_PER_DOMAIN)

    # --- SUMMARY ---
    print(f"\n{'=' * 65}")
    print("  SUMMARY")
    print(f"{'=' * 65}")
    print(f"  Total domain diproses    : {len(domains)}")
    print(f"  G Suite berhasil         : {stats['gsuite_ok']}")
    print(f"  G Suite gagal            : {stats['gsuite_fail']}")
    print(f"  TXT Token berhasil       : {stats['txt_ok']}")
    print(f"  TXT Token gagal          : {stats['txt_fail']}")
    print(f"  Cloudflare Zone OK       : {stats['cf_ok']}")
    print(f"  Cloudflare Zone Gagal    : {stats['cf_fail']}")
    print(f"  DNS Records injected     : {stats['dns_ok']} domain")
    print(f"  Verifikasi berhasil      : {stats['verify_ok']}")
    print(f"  Verifikasi gagal         : {stats['verify_fail']}")
    print(f"  Waktu selesai            : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Log tersimpan di         : {LOG_FILE}")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    main()
