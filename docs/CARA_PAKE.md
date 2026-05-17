# Tutorial gsm (GSuite Manager)

> 1 tool, semua kebutuhan domain + user Workspace lo.

---

## Install (sekali)

```bash
cd gsuite-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# macOS fix (wajib di Python 3.14):
chflags -R nohidden .venv
```

---

## Setup (sekali)

```bash
gsm setup
```

Wizard nanya 3 hal:
1. **CF API Token** → paste dari https://dash.cloudflare.com/profile/api-tokens
2. **CF Account ID** → auto-detect dari token
3. **OAuth file** → auto-detect `credentials.json` / `client_secret_*.json`

Setelah selesai, verify:
```bash
gsm doctor    # target: 5/5 PASS
```

---

## Cara Pake Sehari-hari

### Cara paling simpel: `gsm`

Ketik `gsm` aja tanpa argument → muncul menu:

```
╭────── gsm - Menu Utama ──────╮
│  1. Onboard domains           │
│  2. Create users (bulk)       │
│  3. Reset password (bulk)     │
│  4. Suspend users             │
│  5. Unsuspend users           │
│  6. Audit: CF vs Workspace    │
│  7. Health check DNS          │
│  8. Check domain expiry       │
│  9. List domains              │
│ 10. List users                │
│ 11. Inactive user audit       │
│ 12. Apply DNS template        │
│ 13. Move users to OU          │
│ 14. Ledger stats              │
│ 15. Doctor                    │
│  0. Exit                      │
╰───────────────────────────────╯
Pilih nomor:
```

Ketik nomor → jawab pertanyaan → selesai. Loop sampai ketik `0`.

---

### Cara cepat: `gsm go`

Taruh file di folder yang sama:
- `domains.txt` → 1 domain per baris
- `akun.txt` → format: `email | password | code`

Lalu:
```bash
gsm go
```

Auto-detect kedua file, onboard semua domain, create semua user, print summary. **1 command selesai.**

---

## Fitur Detail (untuk power user)

### Onboard domain ke Workspace

```bash
# 1 domain
gsm domains add example.tech

# Banyak domain
gsm domains add --file domains.txt

# Retry yang DNS-nya belum propagasi
gsm domains verify --only-pending
```

Yang terjadi otomatis per domain:
1. Add ke Google Workspace
2. Ambil TXT verification token
3. Bikin/detect zone di Cloudflare
4. Auto-disable Email Routing (kalo aktif)
5. Inject 5 MX + 1 TXT record
6. Tunggu DNS propagasi (retry otomatis)
7. Trigger Google verify

---

### Create users

```bash
gsm users add --file akun.txt
```

Format `akun.txt`:
```
alice.smith@domain.tech | Password123! | kode-extra
bob@domain.tech | Secret456!
```

---

### Reset password (bulk)

```bash
# Semua user di 1 domain → password sama
gsm users reset-password --domain example.tech --same-password "NewPass123!"

# Random password per user → save ke file
gsm users reset-password --domain example.tech --random --output creds.txt
```

---

### Suspend / Unsuspend users

```bash
# Suspend semua user di domain (block login)
gsm users suspend --domain compromised.tech

# Unsuspend
gsm users unsuspend --domain compromised.tech

# Dari file
gsm users suspend --file bad-users.txt
```

---

### Audit (CF vs Workspace)

```bash
# Lihat gap: domain di CF tapi belum di Workspace
gsm audit

# Save gap ke file → langsung onboard
gsm audit --output gaps.txt
gsm domains add --file gaps.txt
```

---

### Health check DNS

```bash
# Cek semua verified domain: MX/TXT/NS masih bener?
gsm health

# Cek 1 domain
gsm health --domain example.tech
```

---

### Cek domain expiry

```bash
# Alert domain expire dalam 30 hari
gsm check-expiry --days 30
```

---

### Inactive user audit

```bash
# List user yang gak login > 30 hari
gsm users audit --inactive-days 30

# Save ke file (buat suspend/delete)
gsm users audit --inactive-days 60 --output inactive.txt
gsm users suspend --file inactive.txt
```

---

### Apply DNS template (bulk)

Bikin `template.yaml`:
```yaml
records:
  - type: TXT
    name: "@"
    content: "v=spf1 include:_spf.google.com ~all"
  - type: CNAME
    name: "mail"
    content: "ghs.googlehosted.com"
```

```bash
# Preview dulu
gsm dns-apply template.yaml --dry-run

# Apply ke semua verified domain
gsm dns-apply template.yaml

# Apply ke 1 domain aja
gsm dns-apply template.yaml --domain example.tech
```

---

### Move users ke OU

```bash
gsm users move --ou "/Sales" --domain sales-domain.tech
gsm users move --ou "/Engineering" --file engineers.txt
```

---

### Ledger (state management)

```bash
gsm ledger stats                        # lihat statistik
gsm ledger archive --older-than-days 90  # archive record lama
```

---

## Workflow Tipikal

### Onboard batch baru (pagi):
```bash
gsm doctor                    # cek sehat
gsm domains add --file new-domains.txt
gsm users add --file akun.txt
```

### Monitoring (siang):
```bash
gsm audit                     # ada gap?
gsm health                    # DNS sehat?
gsm domains verify --only-pending  # retry pending
```

### Security response (kapan aja):
```bash
gsm users suspend --domain compromised.tech
gsm users reset-password --domain compromised.tech --random --output new-creds.txt
gsm users unsuspend --domain compromised.tech
```

### Cleanup (bulanan):
```bash
gsm users audit --inactive-days 60 --output dead.txt
gsm users suspend --file dead.txt
gsm ledger archive --older-than-days 90
gsm check-expiry --days 30
```

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `No module named 'gsm'` | `chflags -R nohidden .venv` |
| `Configuration is incomplete` | `gsm doctor` → lihat field mana yang missing |
| `cloudflare: token invalid` | `gsm setup --force` → paste token baru |
| `OAuth client file not found` | Ikutin `docs/SETUP_GOOGLE_OAUTH.md` |
| `DNS not propagated` | Tunggu 5 menit → `gsm domains verify --only-pending` |
| `Email Routing blocks MX` | Otomatis di-handle (auto-disable) |
| Domain format salah | gsm reject + kasih saran format yang bener |

---

## Cheatsheet

```
gsm                    # menu interaktif
gsm go                 # auto-detect files, 1 command selesai
gsm setup              # wizard setup awal
gsm doctor             # health check

gsm domains add        # onboard domain
gsm domains verify     # retry pending
gsm domains list       # lihat status
gsm audit              # CF vs Workspace gap
gsm health             # DNS health
gsm check-expiry       # domain expiry

gsm users add          # bulk create
gsm users gen          # auto-generate users
gsm users list         # lihat users
gsm users reset-password  # bulk reset pw
gsm users suspend      # block login
gsm users unsuspend    # unblock
gsm users audit        # inactive users
gsm users move         # pindah OU

gsm dns-apply          # bulk DNS dari template
gsm ledger stats       # statistik
gsm ledger archive     # cleanup lama
gsm --version          # cek versi
```
