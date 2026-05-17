# Quick Action: Rotate CF Token (3 menit)

> **Status sekarang:** Token CF lo (`Qh1dr2J1...`) udah invalid (CF API confirm).
> Tindakan ini wajib sebelum bisa lanjut tes real.

---

## Cara cepet (3 menit)

### Step 1: Buka dashboard CF API Tokens

```
https://dash.cloudflare.com/profile/api-tokens
```

Login pake akun CF lo.

### Step 2: Verify dulu apakah token lama ada

Di list "API Tokens", cari yang nama-nya **start with "Qh1dr2J1"** atau cocok dengan token yang ke-leak.

**Skenario A:** Token gak ada di list
- → Confirmed di-revoke / di-delete sebelumnya
- Lanjut ke Step 3

**Skenario B:** Token ada di list, status "Active"
- → Anomali. Bisa jadi scope salah.
- Cek scope-nya: harus minimal **Zone:Edit** + **DNS:Edit**
- Kalo scope salah: **Roll** token (bikin baru), atau hapus dan bikin baru
- Lanjut ke Step 3

**Skenario C:** Token ada, status "Disabled"
- → Klik "Edit" → tombol enable, atau bikin baru
- Lanjut ke Step 3

### Step 3: Bikin token baru

1. Klik tombol biru **"Create Token"** (kanan-atas)
2. Cari template **"Edit zone DNS"** → klik **"Use template"**
3. Di form yang muncul:
   - **Token name:** `gsuite-manager` (atau bebas)
   - **Permissions:** sudah preset (Zone:Edit, DNS:Edit) - **JANGAN diubah**
   - **Zone Resources:**
     - Pilih dropdown: **"Include"**
     - Sub-dropdown: **"All zones from an account"**
     - Account: pilih account ID `0061a056f8cbc860fb9ec99bd41a0ccc` (yang ada di .env lo)
   - **Client IP Address Filtering:** kosongin (kecuali lo mau strict)
   - **TTL:** kosongin (no expiry) atau set sesuai preferensi lo
4. Klik **"Continue to summary"**
5. Review → klik **"Create Token"**
6. **PENTING:** Token muncul SEKALI. Klik **"Copy"** dan paste ke notes/clipboard
7. Klik **"Verify"** di halaman itu untuk konfirmasi token aktif (otomatis test ke endpoint /verify)

### Step 4: Update `.env`

```bash
cd "/Users/mac/Desktop/Bot/Gsuite Bot"
nano .env
```

Ganti baris:
```
GSM_CF_API_TOKEN=Qh1dr2J1GydCiiIDerH-vGf69k6XQDSToN4MvOIh
```

Jadi:
```
GSM_CF_API_TOKEN=<paste_token_baru_di_sini>
```

Save: Ctrl+O, Enter, Ctrl+X.

### Step 5: Verify

```bash
gsuite-manager/.venv/bin/gsm doctor
```

Target: `cloudflare` row = **PASS**.

---

## Setelah token valid, kabari gua

Cukup tulis ke gua: **"token udah baru"** atau **"doctor PASS"**.

Gua bakal lanjutin:
1. `gsm audit` → tampilin domain CF vs Workspace
2. Kalo ada gap → save ke file dengan `--output gaps.txt`
3. Bulk onboard: `gsm domains add --file gaps.txt`
4. Final audit konfirmasi semua sinkron

---

## Kalo ribet pake nano

Edit pake VSCode / Sublime / TextEdit juga bisa, asal save dengan format plain text (bukan rich text).

### Atau pake sed (one-liner):

```bash
# Backup dulu
cp "/Users/mac/Desktop/Bot/Gsuite Bot/.env" "/Users/mac/Desktop/Bot/Gsuite Bot/.env.bak"

# Replace token (ganti TOKEN_BARU_LO dengan token baru hasil step 3)
sed -i '' 's/GSM_CF_API_TOKEN=.*/GSM_CF_API_TOKEN=TOKEN_BARU_LO/' "/Users/mac/Desktop/Bot/Gsuite Bot/.env"

# Verify
grep GSM_CF_API_TOKEN "/Users/mac/Desktop/Bot/Gsuite Bot/.env"
```

---

## FAQ Cepat

**Q: Token harus per-zone atau all zones?**
A: All zones lebih simpel kalo lo onboard banyak domain baru. Per-zone kalo lo paranoid.

**Q: Setting TTL?**
A: Kalo lo gak yakin, kosongin (no expiry). Bisa di-revoke kapan aja manual.

**Q: Account ID-nya ganti?**
A: Engga. Account ID `0061a056f8cbc860fb9ec99bd41a0ccc` udah benar (gua udah test - ini ID account lo yang ada di .env).

**Q: Lo aman ngasih token ke lo (AI)?**
A: Token disimpen di file `.env` di komputer lo, mode 0o600 (cuma lo yang bisa baca). `.gitignore` block `.env` dari git. Dan token cuma bisa edit DNS/Zone, gak bisa delete account / billing. Worst case kalo bocor: revoke 5 detik dari dashboard.
