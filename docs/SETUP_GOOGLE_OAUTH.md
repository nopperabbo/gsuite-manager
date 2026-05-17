# Setup Google OAuth Desktop App

> Panduan visual step-by-step buat dapetin file `credentials.json` yang dibutuhkan `gsm`.
> Estimasi waktu: **15-30 menit** (sekali setup, gak diulang).

## Kenapa butuh ini?

`gsm` perlu akses Google Workspace lo (buat add domain, bikin user, verify ownership). Itu butuh file OAuth credentials yang lo download dari Google Cloud Console.

---

## Step 1: Buka Google Cloud Console

Buka: **https://console.cloud.google.com**

Login pakai akun **Google Workspace Admin** lo (yang punya akses Admin SDK).

> **Penting:** Akun ini harus admin Workspace, bukan akun Gmail biasa. Kalo lo gak yakin, cek di https://admin.google.com - kalo bisa login, lo admin.

---

## Step 2: Bikin Project Baru

1. Klik **dropdown project** di pojok kiri-atas (di samping "Google Cloud" logo)
2. Di popup yang muncul, klik tombol **"NEW PROJECT"** (kanan-atas)
3. Isi:
   - **Project name:** `gsuite-manager` (atau nama bebas)
   - **Organization:** pilih organization Workspace lo
   - **Location:** biarin default
4. Klik **"CREATE"**
5. Tunggu beberapa detik, lalu **pilih project** itu di dropdown atas

---

## Step 3: Enable 2 API yang Dibutuhkan

`gsm` butuh 2 API:
- **Admin SDK API** (buat manage domain + user)
- **Site Verification API** (buat verify ownership domain)

### Cara enable:

1. Di sidebar kiri, klik **"APIs & Services"** → **"Library"**
2. Search: `Admin SDK API`
3. Klik hasilnya, lalu klik tombol **"ENABLE"** (tunggu sampe selesai)
4. Balik ke Library, search: `Site Verification API`
5. Klik hasilnya, klik **"ENABLE"**

> Kalo udah pernah enable, tombolnya bakal jadi "MANAGE" (artinya udah aktif - skip).

---

## Step 4: Setup OAuth Consent Screen

Sebelum bisa bikin OAuth client, harus setup consent screen dulu.

1. Sidebar: **"APIs & Services"** → **"OAuth consent screen"**
2. Pilih **User Type:**
   - **Internal** kalo lo punya Workspace organization (RECOMMENDED - lebih simpel)
   - **External** kalo gak punya org / pakai Gmail biasa (perlu approval Google)
3. Klik **"CREATE"**
4. Isi form:
   - **App name:** `gsuite-manager` (atau bebas)
   - **User support email:** email Workspace lo
   - **Developer contact:** email Workspace lo
   - Field lain: bisa di-skip
5. Klik **"SAVE AND CONTINUE"**
6. Di **Scopes** page: klik **"SAVE AND CONTINUE"** (gak perlu add scope di sini, scope diatur di code)
7. Di **Test users** page (kalo External): tambahin email lo, klik **"SAVE AND CONTINUE"**
8. Klik **"BACK TO DASHBOARD"**

---

## Step 5: Bikin OAuth Client ID

**Ini step inti yang ngehasilin `credentials.json`.**

1. Sidebar: **"APIs & Services"** → **"Credentials"**
2. Klik **"+ CREATE CREDENTIALS"** (tombol biru di atas)
3. Pilih **"OAuth client ID"**
4. Di form:
   - **Application type:** pilih **"Desktop app"** (PENTING! Bukan Web!)
   - **Name:** `gsuite-manager-cli` (atau bebas)
5. Klik **"CREATE"**
6. Popup muncul dengan **Client ID** dan **Client Secret**
7. **Klik "DOWNLOAD JSON"** (tombol di kanan-bawah popup)

---

## Step 6: Simpen File ke Project

File yang lo download namanya kayak: `client_secret_123456789-abcdef.apps.googleusercontent.com.json`

Pindahin ke folder project:

```bash
# Misal lo download ke ~/Downloads
mv ~/Downloads/client_secret_*.json ./credentials.json

# Atau tetep nama aslinya - gsm auto-detect
mv ~/Downloads/client_secret_*.json ./
```

Verify:

```bash
gsm doctor
```

Cek di output: `oauth_client` row harus **PASS**.

---

## Step 7: First Auth (Browser Login)

Pertama kali run command yang butuh Google API (mis. `gsm domains add`), browser bakal kebuka otomatis:

1. Login pake akun Workspace Admin lo
2. **WARNING screen:** "Google hasn't verified this app" → klik **"Advanced"** → **"Go to gsuite-manager (unsafe)"**
   - Ini muncul karena app lo Internal/Test - aman, ini app lo sendiri
3. Setujui semua scope yang diminta:
   - Site Verification
   - Admin Directory (Domain + User)
4. Setelah selesai, browser nampilin "The authentication flow has completed"
5. Token otomatis disimpen di `token.json` - **gak perlu login lagi sampai 7 hari atau token revoked.**

---

## Troubleshooting

### "App isn't verified" - ada tombol Advanced gak?

Kalo consent screen tipe **External** dan App belum di-publish, hanya test users yang bisa login.

**Fix:** balik ke **OAuth consent screen** → tab **Test users** → tambahin email lo.

### "Access denied" - permission_denied

Akun yang lo pake login bukan Workspace Admin.

**Fix:** Login pake akun yang punya akses ke https://admin.google.com.

### "redirect_uri_mismatch"

Lo bikin OAuth client tipe "Web" instead of "Desktop app".

**Fix:** Bikin OAuth client baru, pilih **Desktop app** (Step 5).

### token.json expired / kena revoke

```bash
rm token.json
gsm doctor   # akan re-auth via browser
```

---

## Security Notes

- `credentials.json` = identitas app lo. **Jangan commit ke git!** (sudah di-block di `.gitignore`)
- `token.json` = akses ke Workspace lo. **Jangan share!** (juga di-block)
- Kalo `credentials.json` ke-leak: revoke di Google Cloud Console → bikin client baru
- Kalo `token.json` ke-leak: balik ke OAuth consent screen → di tab "Credentials" → revoke session
- Mode 0o600 (owner-read-only) di-enforce sama `gsm`

---

## Quick Checklist

- [ ] GCP project bikin
- [ ] Admin SDK API enabled
- [ ] Site Verification API enabled
- [ ] OAuth consent screen configured
- [ ] OAuth client tipe **Desktop app** dibikin
- [ ] JSON downloaded → renamed `credentials.json` → di project root
- [ ] `gsm doctor` → `oauth_client` PASS
- [ ] First command run → browser kebuka → login OK → `token.json` ter-create

Kalo semua ✓, lo siap pake `gsm domains add` dan `gsm users add`.
