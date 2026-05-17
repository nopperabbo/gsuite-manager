# gsuite-manager (`gsm`)

**1 command buat otomatisin Google Workspace + Cloudflare.** Add domain, inject DNS, verify, create users — semua dari terminal.

> 🇮🇩 **Tutorial lengkap (Bahasa Indonesia):** [`docs/CARA_PAKE.md`](docs/CARA_PAKE.md)
>
> 🔧 **Google OAuth setup:** [`docs/SETUP_GOOGLE_OAUTH.md`](docs/SETUP_GOOGLE_OAUTH.md)
>
> 🗺️ **Roadmap:** [`docs/ROADMAP.md`](docs/ROADMAP.md)

---

## Prerequisites

- **Python 3.11+** (`python3 --version`)
- **Google Workspace admin account** (yang bisa login ke https://admin.google.com)
- **Cloudflare account** dengan domain yang udah di-add sebagai zone
- **Google OAuth Desktop App credentials** (file `credentials.json` — cara dapet: [`docs/SETUP_GOOGLE_OAUTH.md`](docs/SETUP_GOOGLE_OAUTH.md))
- **Cloudflare API Token** (cara dapet: https://dash.cloudflare.com/profile/api-tokens → template "Edit zone DNS")

---

## Install

```bash
# 1. Clone repo
git clone https://github.com/nopperabbo/gsuite-manager.git
cd gsuite-manager

# 2. Setup virtualenv + install
python3 -m venv .venv
```

**Activate virtualenv (pilih sesuai OS):**

| OS | Command |
|---|---|
| macOS / Linux | `source .venv/bin/activate` |
| Windows (CMD) | `.venv\Scripts\activate.bat` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |

```bash
# 3. Install dependencies
pip install -e .

# 4. Verify
gsm --version
```

**macOS only (Python 3.14 fix):**
```bash
chflags -R nohidden .venv
```
> Tanpa ini, `gsm` command gak ke-detect di macOS. Linux/Windows gak perlu step ini.

**Linux only (kalo error "No module named venv"):**
```bash
sudo apt install python3-venv   # Debian/Ubuntu
# atau
sudo dnf install python3        # Fedora (sudah include venv)
```

> **Alternatif (semua OS):** `pipx install .` — install global tanpa activate venv tiap kali.

---

## Setup (sekali, interaktif)

```bash
gsm setup
```

Wizard nanya:
1. CF API Token → paste
2. CF Account ID → auto-detect
3. OAuth file → auto-detect

Verify:
```bash
gsm doctor    # target: 5/5 PASS
```

---

## Usage

### Cara paling simpel: ketik `gsm`

```bash
gsm
```

Muncul menu interaktif — pilih nomor, jawab pertanyaan, selesai.

### Cara cepat: `gsm go`

Taruh `domains.txt` dan/atau `akun.txt` di folder, lalu:

```bash
gsm go
```

Auto-detect files, onboard domains + create users, 1 command.

### Command-by-command

```bash
# Onboard domain
gsm domains add example.tech
gsm domains add --file domains.txt

# Auto-generate + create users (tanpa file manual)
gsm users gen --domain example.tech --count 10 --apply

# Atau dari file akun.txt (format: email|password|code)
gsm users add --file akun.txt

# Audit gap CF vs Workspace
gsm audit

# Health check DNS
gsm health

# Reset password bulk
gsm users reset-password --domain example.tech --random --output creds.txt

# Suspend/unsuspend
gsm users suspend --domain compromised.tech
gsm users unsuspend --domain compromised.tech
```

Full command list: `gsm --help` atau lihat [`docs/CARA_PAKE.md`](docs/CARA_PAKE.md)

## Auto-generate akun.txt (Faker, locale-aware)

Males siapin `akun.txt` manual? Pakai `users gen` — generate akun otomatis pakai Faker, locale-aware (Indonesia / English / dll), avoid collision dengan ledger.

```bash
# Preview 50 akun (Indonesia names) — password disembunyikan
gsm users gen --domain bunhe.tech --count 50

# Tulis ke file (compatible sama `gsm users add --file`)
gsm users gen --domain bunhe.tech --count 50 --output akun.txt
gsm users add --file akun.txt

# Atau langsung create ke Workspace dalam 1 step:
gsm users gen --domain bunhe.tech --count 50 --apply

# Custom pattern (default: {first}.{last}@{domain}):
gsm users gen --domain x.com --count 10 --pattern "{first_initial}{last}@{domain}"

# Locale lain (en_US, fr_FR, dll - pass-through ke Faker):
gsm users gen --domain x.com --count 10 --locale en_US

# Reproducible output (testing):
gsm users gen --domain x.com --count 5 --seed 42
```

**Fitur:**
- Locale support: `id_ID` (default), `en_US`, dll — semua locale Faker support
- Collision-aware: skip email yang udah ada di ledger
- Password aman: random 12 char, alphabet tanpa look-alike (0/O/I/l) untuk mengurangi typo waktu handoff ke klien
- File output mode `0600` (POSIX) — protected dari read user lain
- Pattern flexible: `{first}`, `{last}`, `{first_initial}`, `{last_initial}`, `{n}`, `{domain}`

## Auto-check Gmail readiness (MX health check)

Setelah `gsm domains add` selesai, lo bisa verify Gmail udah aktif (MX records udah pointing ke Google) pake `check-mx`. Ga ada API "Gmail aktif?" — yang relevan adalah MX records: kalo udah pointing ke `aspmx.l.google.com` & `alt1-4`, Gmail nerima email.

```bash
# Check 1 domain
gsm domains check-mx bunhe.tech

# Check beberapa sekaligus
gsm domains check-mx bunhe.tech minbu.tech other.com

# Check semua domain VERIFIED di ledger
gsm domains check-mx --all

# Dari file
gsm domains check-mx --file domains.txt

# JSON output (untuk scripting / CI)
gsm domains check-mx bunhe.tech --json | jq '.[].is_healthy'
```

**Status yang mungkin muncul:**

| Status | Arti | Action |
|---|---|---|
| `healthy` | 5/5 MX Google OK | ✓ Gmail siap nerima email |
| `partial` | Sebagian MX Google missing atau priority salah | Run `gsm domains add` (idempotent) |
| `not_google` | MX nunjuk ke provider lain (Outlook, Zoho, dll) | Decide: pindah ke Google atau biarin |
| `no_mx` | Domain ga punya MX sama sekali | Run `gsm domains add` untuk inject |
| `error` | DNS lookup gagal (NXDOMAIN, timeout) | Cek nameserver, propagation |

Exit code: `0` kalo semua healthy, `1` kalo ada satu pun yang gak healthy. Pas buat dipake di CI / cron untuk monitoring.

## Auto-import zone dari Cloudflare

Reseller punya 30 zone di CF account, mau onboard semua sekaligus? Pake `domains import`. Default mode = interactive picker (lo bisa centang per-domain), atau `--all` buat skip ke onboard semua.

```bash
# Interactive picker (default) - tampilkan list, lo centang yang mau di-onboard
gsm domains import

# Skip picker, langsung onboard semua zone yang belum VERIFIED
gsm domains import --all

# Filter glob (case-insensitive)
gsm domains import --filter "*.tech"

# Preview saja (gak onboard apa-apa)
gsm domains import --dry-run

# Tulis daftar terpilih ke file (bisa di-pipe ke `domains add --file`)
gsm domains import --output selected.txt
gsm domains add --file selected.txt
```

**Cara kerja default mode:**
1. `gsm` fetch semua zone dari Cloudflare account lo
2. Cross-reference sama ledger:
   - **NEW** (belum pernah di-import) → centang otomatis ✓
   - **In progress** (status di ledger: PENDING/DNS_PENDING/dll) → opsional, default uncheck
   - **VERIFIED** (sudah selesai) → di-skip otomatis (gak muncul di picker)
3. Lo space-bar buat toggle, enter buat confirm
4. Yang lo pilih → masuk ke pipeline `onboard_domains` (sama kek `domains add`)

## Quickstart (manual venv path)

```bash
cd gsuite-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
gsm setup    # or gsm init for non-interactive scaffolding
```

## What this fixes

The legacy scripts in `legacy/` worked but had several pain points. Each was addressed deliberately:

| Pain point | Fix in `gsm` |
|---|---|
| Hardcoded secrets in source | All config via `.env` (validated) |
| 271 DNS propagation failures in production | DNS pre-check via dnspython against 8.8.8.8 + 1.1.1.1 with tiered backoff before triggering Google verify |
| No idempotency, re-run = full re-run | JSON ledger tracks per-domain status (PENDING → GSUITE_ADDED → ... → VERIFIED) |
| Manual edit of failed-domain list | `gsm domains verify --only-pending` |
| 3 separate scripts, duplicate auth code | Single CLI, shared core |
| `akun.txt` resolved to wrong path (parent of script dir) | Resolved relative to CWD, explicit `--file` flag |
| Hardcoded list of ~200 first names for splitting | Dropped: simpler rule (split on '.' or fall back to local-part + "User") |
| MX inject blocked by CF Email Routing | Auto-detect + auto-disable Email Routing before MX inject (logged + idempotent) |
| No view of state mismatch between CF + Workspace | `gsm audit` lists gap: CF-only vs Workspace-only domains |

## Architecture

```
src/gsm/
├── cli/         # Typer commands: domains, users, init, doctor
├── clients/     # External API wrappers: cloudflare, google_admin, google_verify, dns_check
├── core/        # config, auth (OAuth Desktop), logging
├── workflows/   # Orchestration: domain_onboarding, user_bulk_create
├── models/      # Pydantic types: domain, user, results
└── state/       # JSON ledger
```

## Development

```bash
pip install -e ".[dev]"

# Lint + format
ruff check src tests
ruff format src tests

# Type check
mypy src

# Tests
pytest

# End-to-end smoke (offline)
scripts/smoke_test.sh

# End-to-end smoke including real `gsm doctor` against current .env
scripts/smoke_test.sh --with-real-doctor
```

Current status: **111 tests passing, 87% coverage, ruff + mypy strict clean.**

## Security notes

- `.env`, `credentials.json`, `client_secret_*.json`, `token.json`, `gsm_state.json` are all gitignored.
- The `gsm init` wizard writes `.env` with mode `0600`.
- The OAuth token cache (`token.json`) is written with mode `0600`.
- **Before production use**: rotate any Cloudflare API token / OAuth client secret that was previously committed to a repo or shared in plaintext. See [`docs/PRODUCTION_RUNBOOK.md`](docs/PRODUCTION_RUNBOOK.md) for step-by-step instructions.

## Production runbook

For the rotation steps, real-domain smoke test procedure, and bulk-user smoke test, see [`docs/PRODUCTION_RUNBOOK.md`](docs/PRODUCTION_RUNBOOK.md).

## Project plan

See `.sisyphus/plans/02-gsuite-manager-foundation-v2.md` for the full architecture spec and acceptance criteria.
