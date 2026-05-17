# Cara Test gsuite-manager Sendiri

> Tutorial buat lo test project ini step-by-step. Bagi 2 tier:
> **Tier 1** (5 menit) - cek instalasi & CLI tanpa sentuh API real
> **Tier 2** (15-30 menit) - 1 domain test end-to-end (butuh CF token valid)

---

## TIER 1: Smoke Test (Tanpa Risiko, 5 Menit)

Tujuan: pastiin install bersih, semua command jalan, gak ada error tersembunyi.

### Step 1: Buka terminal di folder project

```bash
cd "/Users/mac/Desktop/Bot/Gsuite Bot/gsuite-manager"
```

### Step 2: Workaround macOS hidden flag (sekali aja)

```bash
chflags -R nohidden .venv
```

> Penjelasan: macOS auto-hide folder `.venv`, Python 3.14 jadi nge-skip .pth file di dalamnya. Workaround ini bikin .venv dianggap visible.

### Step 3: Cek CLI nyala

```bash
.venv/bin/gsm --version
.venv/bin/gsm --help
```

Yang harus muncul:
- `gsm 0.1.0`
- Help dengan 6 command: `setup`, `init`, `doctor`, `domains`, `users`, `ledger`

**Kalo error `No module named 'gsm'`:** ulangi Step 2.

### Step 4: Run automated smoke test

```bash
bash scripts/smoke_test.sh
```

Yang harus muncul:
```
==> 1. CLI: --help                      OK
==> 2. CLI: domains/users subcommands   OK
==> 3. CLI: init writes .env into temp dir  OK
==> 4. Tests + lint + types             OK

All smoke checks passed.
```

### Step 5: Run unit tests

```bash
.venv/bin/python -m pytest -q
```

Yang harus muncul:
```
167 passed, 1 skipped in ~2s
```

> Yang skipped itu test `python -m gsm` subprocess - normal di env lo karena path-with-spaces quirk.

### Step 6: Cek wizard `gsm setup --help`

```bash
.venv/bin/gsm setup --help
```

Harus muncul help dengan 3 options: `--cwd`, `--force`, `--skip-test`.

### Step 7: Cek pre-flight reject domain salah format

```bash
.venv/bin/gsm domains add BadDomain.COM 2>&1 | tail -10
```

Yang harus muncul:
- Tabel dengan status `failed`
- Pesan error: `Domain harus huruf kecil tanpa whitespace. Gunakan: baddomain.com`

> Ini bukti pre-flight check jalan.

### Step 8: Cek friendly error untuk config kosong

Buka terminal baru, ke folder kosong:
```bash
cd /tmp && mkdir -p gsm-test-empty && cd gsm-test-empty
"/Users/mac/Desktop/Bot/Gsuite Bot/gsuite-manager/.venv/bin/gsm" doctor
```

Yang harus muncul:
- Tabel doctor dengan row `settings` = FAIL
- Pesan jelas: "Field required: cf_api_token, cf_account_id"
- **TIDAK ADA Python traceback bertumpuk-tumpuk**

### Tier 1 Pass Criteria

- [ ] `gsm --version` cetak `0.1.0`
- [ ] `gsm --help` tampil 6 command
- [ ] `bash scripts/smoke_test.sh` → "All smoke checks passed"
- [ ] `pytest -q` → 167 passed
- [ ] Pre-flight reject `BadDomain.COM` dengan saran lowercase
- [ ] Doctor di folder tanpa .env → friendly error, no traceback

Kalo semua ✓, **Tier 1 lulus.** CLI ekat, install sehat.

---

## TIER 2: Real Test (1 Domain, 15-30 Menit)

Tujuan: validasi end-to-end pipeline pakai 1 domain throwaway.

### Persiapan (one-time)

#### 2A. Rotate CF API token

Token lama yang ada di `legacy/gsuite_cloudflare_bot.py` udah ke-leak. Bikin baru:

1. Buka https://dash.cloudflare.com/profile/api-tokens
2. Klik "Create Token"
3. Pilih template "Edit zone DNS"
4. Account: pilih account lo
5. Zone Resources: "All zones" (atau specific zones)
6. Klik "Continue to summary" → "Create Token"
7. **Copy tokennya** (hanya muncul sekali!)

#### 2B. Cek file OAuth credentials.json

```bash
ls /Users/mac/Desktop/Bot/Gsuite\ Bot/client_secret_*.json
```

Kalo ada file tersebut, lo udah punya credentials. Kalo gak ada:
- Ikutin `docs/SETUP_GOOGLE_OAUTH.md` step-by-step

#### 2C. Run wizard setup

```bash
cd "/Users/mac/Desktop/Bot/Gsuite Bot"
"/Users/mac/Desktop/Bot/Gsuite Bot/gsuite-manager/.venv/bin/gsm" setup
```

Wizard bakal nanya:
1. **CF API Token**: paste token yang baru lo copy
2. **CF Account ID**: dia auto-detect dari token, lo cuma confirm `y`
3. **OAuth client path**: dia auto-detect file `client_secret_*.json`, lo confirm `y`
4. **Test koneksi**: harus PASS dengan status "active"

Yang harus muncul:
```
[+] Setup selesai!
  Settings: /Users/mac/Desktop/Bot/Gsuite Bot/.env
  OAuth file: ./client_secret_xxx.json (ada)
```

#### 2D. Verify dengan doctor

```bash
gsuite-manager/.venv/bin/gsm doctor
```

Target: **5/5 PASS**. Kalo masih ada FAIL, fix dulu sebelum lanjut Tier 2 main test.

### Main Test: 1 Domain End-to-End

> **PENTING:** Pakai domain throwaway yang lo OK kalo error / di-add ke Workspace lo.
> Lo bisa register .tech murah ($1-3) di Namecheap/Porkbun khusus buat tes.

#### Step 1: Onboard 1 domain

```bash
cd "/Users/mac/Desktop/Bot/Gsuite Bot"
gsuite-manager/.venv/bin/gsm domains add my-test-domain.tech
```

Yang lo expect (urut):
1. Browser OAuth muncul (kalo pertama kali) → login Workspace admin → setujui scope
2. `step_add_gsuite` log → domain ke-add ke Workspace
3. `step_fetch_token` log → ambil TXT verification token
4. `step_ensure_zone` log → bikin zone di CF
5. `step_inject_dns` log → inject 5 MX + 1 TXT record
6. `step_wait_dns` log → poll DNS propagasi (bisa 1-5 menit)
7. `step_verify` log → trigger Google verify
8. Hasil akhir: tabel dengan status **success**

Total waktu: **3-10 menit** tergantung DNS propagasi.

#### Step 2: Cek state ke-tracked

```bash
gsuite-manager/.venv/bin/gsm domains list
```

Domain lo harus muncul dengan status `verified`.

```bash
gsuite-manager/.venv/bin/gsm ledger stats
```

Harus muncul `domains_verified: 1`.

#### Step 3: Test idempotency

Run lagi command yang sama:

```bash
gsuite-manager/.venv/bin/gsm domains add my-test-domain.tech
```

Yang harus muncul:
- Status: **skipped** dengan pesan "already verified"
- **Tidak ada panggilan API yang re-trigger**

> Kalo dia trigger ulang dari awal, idempotency rusak (bug).

#### Step 4: Test verify --only-pending (skenario DNS slow)

Skenario: domain yang DNS-nya belum propagasi.

```bash
gsuite-manager/.venv/bin/gsm domains add another-test.tech
# Misal DNS belum propagasi - dia jadi DNS_PENDING
```

Lalu retry:
```bash
gsuite-manager/.venv/bin/gsm domains verify --only-pending
```

Yang harus muncul:
- Cuma cek domain dengan status `DNS_PENDING` atau `DNS_INJECTED`
- Skip yang `verified`

### Optional: Test Bulk Users

#### Bikin akun.txt minimal:

```bash
cat > akun.txt <<EOF
testuser1@my-test-domain.tech | TestPass123! | code-1
testuser2@my-test-domain.tech | TestPass123! | code-2
EOF
```

#### Run:

```bash
gsuite-manager/.venv/bin/gsm users add --file akun.txt
```

Yang harus muncul:
- Progress bar: 2 user, ETA, dll
- Tabel hasil: 2 success
- `gsm users list` → 2 user appear

#### Cleanup user (manual via Admin Console):

User Workspace yang testuser1 / testuser2 perlu lo delete via https://admin.google.com/ kalo mau bersih.

### Tier 2 Pass Criteria

- [ ] `gsm setup` wizard jalan tanpa error, test koneksi PASS
- [ ] `gsm doctor` 5/5 PASS
- [ ] `gsm domains add my-test.tech` end-to-end success (verified)
- [ ] `gsm domains list` tampil domain dengan status verified
- [ ] Re-run `gsm domains add` same domain → skipped (idempotent)
- [ ] `gsm users add` bikin user, tampil di `gsm users list`

Kalo semua ✓, **lo udah validasi project secara real.** Aman pake produksi.

---

## Cleanup setelah test

### Remove test domain dari Workspace:
1. Buka https://admin.google.com → Domains → Manage domains
2. Find domain test, delete

### Remove test domain dari Cloudflare:
1. Buka https://dash.cloudflare.com → pilih domain
2. Settings → Advanced Actions → Delete Zone

### Remove test users:
1. Buka https://admin.google.com → Users
2. Find testuser1/testuser2, delete

### Hapus state local:
```bash
rm gsm_state.json gsm_state.json.archive.json akun.txt 2>/dev/null
```

---

## Skenario Bug Hunt (Optional - Stress Test)

Kalo lo iseng pengen tes lebih edge case:

### Test 1: Corrupt ledger recovery
```bash
echo 'GARBAGE NOT JSON' > gsm_state.json
gsuite-manager/.venv/bin/gsm domains list
# Expected: "(no domains in ledger)"
ls gsm_state.json.corrupt-*   # corrupt file di-backup
```

### Test 2: Empty akun.txt
```bash
touch empty_akun.txt
gsuite-manager/.venv/bin/gsm users add --file empty_akun.txt
# Expected: friendly message, no crash
```

### Test 3: Malformed akun.txt
```bash
cat > bad_akun.txt <<EOF
# only comments
@invalid | pw
local@nodot | pw
valid@example.com | pw
EOF
# Run dry mode (just parse, don't create):
.venv/bin/python -c "
from gsm.workflows.user_bulk_create import parse_akun_file
from pathlib import Path
print(parse_akun_file(Path('bad_akun.txt')))
"
# Expected: cuma valid@example.com yang lolos
```

### Test 4: Wrong CF token
Edit `.env` ganti GSM_CF_API_TOKEN ke token salah, run:
```bash
gsuite-manager/.venv/bin/gsm doctor
```
Expected: cloudflare row FAIL dengan "token invalid"

### Test 5: Network disconnect (simulasi)
Disable WiFi, run:
```bash
gsuite-manager/.venv/bin/gsm domains add some-domain.com
```
Expected: friendly error "Koneksi internet bermasalah ke server" (bukan raw stacktrace)

---

## Troubleshooting Cepat

| Gejala | Solusi |
|---|
| `No module named 'gsm'` | Run `chflags -R nohidden .venv` |
| `OAuth client file not found` | Cek file `credentials.json` ada di CWD lo |
| `cloudflare: token invalid` | Run `gsm setup --force` ulang dengan token baru |
| `DNS verification token could not be found` | Tunggu 5 menit, run `gsm domains verify --only-pending` |
| Browser OAuth gak kebuka | Pastiin gak running di SSH/headless server |
| `permission denied` saat install | Pakai `pipx install .` atau `pip install --user` |

---

## Yang Harus Lo Verify

Inti tutorial ini: lo bisa **percaya tool ini sebelum bikin commit ke production batch**.

**Tier 1 cukup buat conviction "tool gak crash".**
**Tier 2 cukup buat conviction "tool benar-benar bekerja end-to-end".**

Kalo dua-duanya pass, lo siap onboard 150 domain real lo.

Selamat tes. Kabar lo kalo nemu yang aneh - gua bakal fix.
