#!/usr/bin/env python3
"""
=============================================================================
  Google Workspace - Bulk User Creator (Gmail Activation)
=============================================================================
  Baca akun dari akun.txt, buat user di Google Workspace via Admin SDK.
  Format akun.txt:  email@domain.tech | password | kode
  
  Setelah user dibuat, Gmail otomatis aktif untuk user tersebut.

  Dependensi:
    pip install google-auth google-auth-oauthlib google-api-python-client
=============================================================================
"""

import sys
import os
import time
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# ===========================================================================
#  KONFIGURASI
# ===========================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AKUN_FILE = os.path.join(os.path.dirname(SCRIPT_DIR), "akun.txt")
GOOGLE_OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "user_creation_log.txt")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/siteverification",
    "https://www.googleapis.com/auth/admin.directory.domain",
    "https://www.googleapis.com/auth/admin.directory.user",
]

DELAY_PER_USER = 1  # detik antar user (anti rate-limit)


# ===========================================================================
#  LOGGING
# ===========================================================================

def log(level, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "ok":   "[+]",
        "fail": "[-]",
        "info": "[*]",
        "warn": "[!]",
    }.get(level, "[?]")
    print(f"{ts} {prefix} {msg}", flush=True)


# ===========================================================================
#  AUTH
# ===========================================================================

def detect_oauth_client_file():
    for filename in os.listdir(SCRIPT_DIR):
        if filename == "credentials.json":
            return os.path.join(SCRIPT_DIR, filename)
    for filename in os.listdir(SCRIPT_DIR):
        if filename.startswith("client_secret_") and filename.endswith(".json"):
            return os.path.join(SCRIPT_DIR, filename)
    return None


def build_admin_service():
    oauth_client_file = detect_oauth_client_file()
    if not oauth_client_file:
        log("fail", "File OAuth client JSON tidak ditemukan di folder script.")
        sys.exit(1)

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
            log("ok", "OAuth token berhasil di-refresh.")
        except Exception:
            credentials = None

    if not credentials or not credentials.valid:
        # Check if existing token has all required scopes
        needs_reauth = True
        if credentials and credentials.valid:
            needs_reauth = False

        if needs_reauth:
            log("info", "Login browser diperlukan (scope baru: admin.directory.user)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                oauth_client_file, GOOGLE_SCOPES
            )
            credentials = flow.run_local_server(port=0)
            with open(GOOGLE_OAUTH_TOKEN_FILE, "w") as f:
                f.write(credentials.to_json())
            log("ok", "Login berhasil, token disimpan.")

    admin_service = build("admin", "directory_v1", credentials=credentials)
    return admin_service


# ===========================================================================
#  PARSE AKUN.TXT
# ===========================================================================

def parse_akun_file(filepath):
    accounts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or "@" not in line:
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue

            email = parts[0]
            password = parts[1]

            if not email or "@" not in email:
                continue

            accounts.append({
                "email": email,
                "password": password,
                "line_num": line_num,
            })

    return accounts


# ===========================================================================
#  CREATE USER
# ===========================================================================

def create_user(admin_service, email, password):
    username = email.split("@")[0]

    # Split username into first/last name
    # Try common patterns: firstlast, first.last
    if "." in username:
        parts = username.split(".", 1)
        first_name = parts[0].capitalize()
        last_name = parts[1].capitalize()
    else:
        # Try to split camelCase or just use as-is
        # For names like "raymondrodgers" - heuristic split
        first_name = username.capitalize()
        last_name = "User"

        # Try to find a reasonable split point (common name patterns)
        common_first_names = [
            "michael", "james", "john", "robert", "david", "william", "richard",
            "joseph", "thomas", "charles", "christopher", "daniel", "matthew",
            "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua",
            "kenneth", "kevin", "brian", "george", "timothy", "ronald", "edward",
            "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas", "eric",
            "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin",
            "samuel", "raymond", "gregory", "frank", "alexander", "patrick", "jack",
            "dennis", "jerry", "tyler", "aaron", "jose", "adam", "nathan", "henry",
            "douglas", "zachary", "peter", "kyle", "noah", "ethan", "jeremy",
            "walter", "christian", "keith", "roger", "terry", "austin", "sean",
            "gerald", "carl", "harold", "dylan", "arthur", "lawrence", "jordan",
            "jesse", "bryan", "billy", "bruce", "gabriel", "joe", "logan", "albert",
            "willie", "alan", "eugene", "vincent", "russell", "elijah", "randy",
            "philip", "harry", "bobby", "johnny", "howard", "lance", "dustin",
            # Female names
            "mary", "patricia", "jennifer", "linda", "barbara", "elizabeth",
            "susan", "jessica", "sarah", "karen", "lisa", "nancy", "betty",
            "margaret", "sandra", "ashley", "dorothy", "kimberly", "emily",
            "donna", "michelle", "carol", "amanda", "melissa", "deborah",
            "stephanie", "rebecca", "sharon", "laura", "cynthia", "kathleen",
            "amy", "angela", "shirley", "anna", "brenda", "pamela", "emma",
            "nicole", "helen", "samantha", "katherine", "christine", "debra",
            "rachel", "carolyn", "janet", "catherine", "maria", "heather",
            "diane", "ruth", "julie", "olivia", "joyce", "virginia", "victoria",
            "kelly", "lauren", "christina", "joan", "evelyn", "judith", "megan",
            "andrea", "cheryl", "hannah", "jacqueline", "martha", "gloria",
            "teresa", "ann", "sara", "madison", "frances", "kathryn", "janice",
            "jean", "abigail", "alice", "judy", "sophia", "grace", "denise",
            "amber", "doris", "marilyn", "danielle", "beverly", "isabella",
            "theresa", "diana", "natalie", "brittany", "charlotte", "marie",
            "kayla", "alexis", "lori", "tina", "tara", "stacy", "monica",
            "courtney", "sonia", "ariel", "kelsey", "valerie", "destiny",
            "ronnie", "christie",
        ]

        lower = username.lower()
        for name in sorted(common_first_names, key=len, reverse=True):
            if lower.startswith(name) and len(lower) > len(name):
                first_name = name.capitalize()
                last_name = lower[len(name):].capitalize()
                break

    body = {
        "primaryEmail": email,
        "name": {
            "givenName": first_name,
            "familyName": last_name,
        },
        "password": password,
        "changePasswordAtNextLogin": False,
    }

    try:
        result = admin_service.users().insert(body=body).execute()
        return True, f"Created {email}"
    except Exception as e:
        err = str(e)
        if "409" in err or "already exists" in err.lower() or "duplicate" in err.lower():
            return True, f"Already exists (skip)"
        elif "domain" in err.lower() and "not found" in err.lower():
            return False, f"Domain not in G Suite"
        else:
            return False, err[:200]


# ===========================================================================
#  MAIN
# ===========================================================================

def main():
    log("info", "=" * 60)
    log("info", "  Google Workspace - Bulk User Creator")
    log("info", "=" * 60)

    if not os.path.exists(AKUN_FILE):
        log("fail", f"File akun tidak ditemukan: {AKUN_FILE}")
        sys.exit(1)

    accounts = parse_akun_file(AKUN_FILE)
    log("info", f"Ditemukan {len(accounts)} akun valid di akun.txt")

    admin_service = build_admin_service()
    log("ok", "Admin SDK service berhasil dibuat")

    success_count = 0
    skip_count = 0
    fail_count = 0
    results = []

    for i, account in enumerate(accounts, 1):
        email = account["email"]
        password = account["password"]

        print(f"\n{'─' * 55}")
        log("info", f"[{i}/{len(accounts)}] Creating user: {email}")
        print(f"{'─' * 55}")

        ok, msg = create_user(admin_service, email, password)

        if ok:
            if "Already exists" in msg:
                log("info", f"  {msg}")
                skip_count += 1
                results.append(f"SKIP | {email} | {msg}")
            else:
                log("ok", f"  {msg}")
                success_count += 1
                results.append(f"OK   | {email}")
        else:
            log("fail", f"  GAGAL: {msg}")
            fail_count += 1
            results.append(f"FAIL | {email} | {msg}")

        if i < len(accounts):
            time.sleep(DELAY_PER_USER)

    # Summary
    print(f"\n{'=' * 60}")
    log("info", "  SUMMARY")
    print(f"{'=' * 60}")
    log("info", f"  Total akun diproses  : {len(accounts)}")
    log("ok",   f"  Berhasil dibuat      : {success_count}")
    log("info", f"  Sudah ada (skip)     : {skip_count}")
    log("fail", f"  Gagal                : {fail_count}")
    log("info", f"  Waktu selesai        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("info", f"  Log tersimpan di     : {LOG_FILE}")
    print(f"{'=' * 60}")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"User Creation Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total: {len(accounts)} | OK: {success_count} | Skip: {skip_count} | Fail: {fail_count}\n")
        f.write("=" * 60 + "\n")
        for r in results:
            f.write(r + "\n")


if __name__ == "__main__":
    main()
