# Research: Gap Analysis - gsm vs Real GSuite Admin Needs

> Hasil research mendalam: apa yang gsm SUDAH solve vs apa yang masih MISSING
> untuk admin yang manage 400+ domain + ratusan user.

---

## Yang gsm SUDAH Solve ✅

| Problem | Solution | Status |
|---|---|---|
| Manual domain onboarding (repetitif) | `gsm domains add` (7-step pipeline) | ✅ Tested real |
| DNS race condition (271 failures) | DNS pre-check + backoff | ✅ |
| CF Email Routing blocks MX | Auto-disable before inject | ✅ |
| Manual user creation | `gsm users add` + `users gen` (auto) | ✅ |
| Gak tau domain mana yang gap | `gsm audit` (CF vs Workspace) | ✅ |
| DNS rusak tanpa sadar | `gsm health` (MX/TXT/NS check) | ✅ |
| Domain expire tanpa alert | `gsm check-expiry` (RDAP) | ✅ |
| Password reset manual 1-1 | `gsm users reset-password` (bulk) | ✅ |
| Suspend user manual | `gsm users suspend/unsuspend` | ✅ |
| Dead accounts gak ketauan | `gsm users audit --inactive-days` | ✅ |
| Bulk DNS changes | `gsm dns-apply` (YAML template) | ✅ |
| OU management | `gsm users move --ou` | ✅ |
| No idempotency (re-run = chaos) | Ledger state machine | ✅ |
| Setup ribet | `gsm setup` wizard + `gsm` menu | ✅ |

---

## Yang BELUM Solve ❌ (Gap Analysis)

### 🔴 CRITICAL - Pasti kena sekarang

#### 1. Email Deliverability (SPF/DKIM/DMARC)

**Problem:** 400 domain onboarded tapi TANPA SPF/DKIM/DMARC = semua email keluar masuk SPAM di penerima.

**Detail:**
- **SPF** (Sender Policy Framework) — bilang ke dunia "email dari domain ini cuma boleh dikirim dari server Google". Tanpa ini: email dianggap spoofed.
- **DKIM** (DomainKeys Identified Mail) — tanda tangan digital per email. Google auto-sign, tapi domain harus punya CNAME record yang point ke Google DKIM key.
- **DMARC** (Domain-based Message Authentication) — policy: apa yang harus dilakukan kalo SPF/DKIM gagal (reject/quarantine/none).

**Impact:** SETIAP email yang dikirim dari 400 domain lo kemungkinan besar masuk spam folder penerima. Ini bukan "nice to have" — ini broken email.

**Yang dibutuhkan gsm:**
```bash
gsm email-auth setup --domain example.tech
# Auto-inject: SPF TXT record + DKIM CNAME records + DMARC TXT record

gsm email-auth check
# Audit semua domain: mana yang SPF/DKIM/DMARC-nya missing

gsm email-auth fix --all
# Bulk fix semua domain yang missing
```

**Records yang perlu di-inject:**
```
TXT  @           "v=spf1 include:_spf.google.com ~all"
TXT  _dmarc      "v=DMARC1; p=none; rua=mailto:dmarc@example.tech"
CNAME google._domainkey  google._domainkey.example.tech.s1234.dkim.googlehosted.com
```

**Effort:** ~3-4 jam (DKIM butuh query Google Admin API untuk dapet selector per domain)

---

#### 2. Bulk Delete Users

**Problem:** Setelah `gsm users audit --inactive-days 60` kasih list dead accounts, gak ada cara delete mereka. Cuma bisa suspend.

**Yang dibutuhkan:**
```bash
gsm users delete --file inactive.txt
gsm users delete --domain old-domain.tech --confirm
```

**Concern:** Delete = permanent (30 hari recovery window di Google). Butuh confirmation dialog yang kuat.

**Effort:** ~1 jam

---

#### 3. Export Users ke CSV/File

**Problem:** Gak bisa export list user + status ke file buat reporting/backup.

**Yang dibutuhkan:**
```bash
gsm users export --domain example.tech --output users.csv
gsm users export --all --output all-users.csv
# Format: email, first_name, last_name, status, last_login, created_date
```

**Effort:** ~1 jam

---

### 🟡 HIGH - Kemungkinan besar dibutuhkan

#### 4. 2FA/MFA Audit

**Problem:** Google Workspace support 2FA tapi gak enforce by default. Admin gak tau user mana yang BELUM enable 2FA = security hole.

**Yang dibutuhkan:**
```bash
gsm security 2fa-audit
# List user yang belum enable 2FA

gsm security 2fa-audit --domain example.tech --output no-2fa.txt
```

**Effort:** ~1 jam (Google Admin API punya field `isEnrolledIn2Sv`)

---

#### 5. Email Aliases Management

**Problem:** Bisnis domain sering butuh alias (info@, support@, admin@ → forward ke user tertentu). Sekarang harus manual di Admin Console.

**Yang dibutuhkan:**
```bash
gsm users alias add user@domain.tech --alias info@domain.tech
gsm users alias add user@domain.tech --alias support@domain.tech
gsm users alias list --domain domain.tech
gsm users alias remove info@domain.tech
```

**Effort:** ~2 jam

---

#### 6. Cron-Friendly Output (--json flag)

**Problem:** Kalo mau schedule `gsm health` atau `gsm audit` via cron + alert ke Telegram/Slack, output Rich table gak parseable.

**Yang dibutuhkan:**
```bash
gsm health --json > health.json
gsm audit --json > audit.json
gsm check-expiry --json > expiry.json

# Contoh cron + alert:
gsm health --json | jq '.issues | length' | xargs -I{} test {} -gt 0 && curl telegram...
```

**Effort:** ~2 jam (add --json flag ke semua monitoring commands)

---

#### 7. Groups/Mailing Lists

**Problem:** Workspace Groups (mailing lists) sering dibutuhkan: all@domain.tech, team@domain.tech. Sekarang manual.

**Yang dibutuhkan:**
```bash
gsm groups create all@domain.tech --members-from users.txt
gsm groups list --domain domain.tech
gsm groups add-member team@domain.tech user1@domain.tech user2@domain.tech
```

**Effort:** ~3 jam (Google Groups API)

---

### 🟢 NICE-TO-HAVE - Buat scale lebih gede

#### 8. License Management

**Problem:** Workspace punya tiers (Business Starter/Standard/Plus). Assign license per user = manual.

**Effort:** ~2 jam

#### 9. Shared Drive Management

**Problem:** Create/manage shared drives buat tim.

**Effort:** ~2 jam

#### 10. Admin Role Assignment

**Problem:** Assign admin roles (Super Admin, User Management Admin, dll) ke user.

**Effort:** ~1 jam

#### 11. Login Audit Log

**Problem:** Siapa login dari mana, kapan. Suspicious activity detection.

**Effort:** ~3 jam (Google Reports API)

#### 12. Webhook/Notification on Failure

**Problem:** Kalo batch run gagal di tengah, gak ada alert. User harus manual cek.

**Effort:** ~2 jam

---

## Prioritas Rekomendasi

| # | Feature | Impact | Effort | ROI |
|---|---|---|---|---|
| **1** | **SPF/DKIM/DMARC** | 🔴 Email lo masuk spam SEKARANG | 3-4 jam | **HIGHEST** |
| **2** | **Bulk delete users** | 🔴 Cleanup setelah audit | 1 jam | High |
| **3** | **Export users CSV** | 🟡 Reporting/backup | 1 jam | High |
| **4** | **2FA audit** | 🟡 Security compliance | 1 jam | High |
| **5** | **--json output** | 🟡 Automation/cron | 2 jam | High |
| **6** | **Email aliases** | 🟡 Business need | 2 jam | Medium |
| **7** | **Groups/mailing lists** | 🟡 Team management | 3 jam | Medium |
| 8 | License management | 🟢 Cost optimization | 2 jam | Low |
| 9 | Shared drives | 🟢 Collaboration | 2 jam | Low |
| 10 | Admin roles | 🟢 Delegation | 1 jam | Low |
| 11 | Login audit | 🟢 Security monitoring | 3 jam | Low |
| 12 | Webhook alerts | 🟢 Ops automation | 2 jam | Low |

---

## Competitor Comparison

| Feature | gsm (kita) | GAM (Google Apps Manager) | Admin Console (web) |
|---|---|---|---|
| Domain onboarding pipeline | ✅ Full auto | ❌ Manual steps | ❌ Manual |
| Cloudflare integration | ✅ Native | ❌ Gak ada | ❌ Gak ada |
| DNS health monitoring | ✅ | ❌ | ❌ |
| Email Routing auto-disable | ✅ | ❌ | ❌ |
| Interactive menu | ✅ | ❌ CLI only | ✅ Web UI |
| Idempotent state machine | ✅ | ❌ | ❌ |
| User CRUD | ✅ Basic | ✅ Full (500+ commands) | ✅ |
| SPF/DKIM/DMARC | ❌ **MISSING** | ✅ | ✅ (manual) |
| Groups management | ❌ **MISSING** | ✅ | ✅ |
| 2FA audit | ❌ **MISSING** | ✅ | ✅ |
| Email aliases | ❌ **MISSING** | ✅ | ✅ |
| Calendar/Drive management | ❌ Out of scope | ✅ | ✅ |
| Bulk delete | ❌ **MISSING** | ✅ | ✅ (slow) |
| JSON output | ❌ **MISSING** | ✅ | ❌ |
| Export CSV | ❌ **MISSING** | ✅ | ✅ |

**Unique value gsm vs GAM:** CF integration + domain pipeline + DNS monitoring + interactive UX.
**Gap vs GAM:** email auth, groups, aliases, delete, export, JSON output.

---

## Rekomendasi Strategi

### Option A: "Domain-Focused Tool" (stay niche)
Tambah cuma #1 (SPF/DKIM/DMARC) + #2 (delete) + #3 (export). Sisanya bilang "pake Admin Console atau GAM".
- Pro: Focused, maintainable, clear value prop
- Con: User masih perlu tool lain buat daily ops

### Option B: "Full Workspace Manager" (compete with GAM)
Tambah semua #1-#7. Jadi one-stop-shop.
- Pro: User gak perlu tool lain
- Con: Scope besar, maintenance burden, GAM udah mature

### Option C: "Smart Hybrid" (RECOMMENDED)
Tambah #1-#5 (critical + high impact, total ~8 jam). Sisanya defer.
- Pro: Cover 90% daily needs, still focused
- Con: Groups/aliases masih manual

---

## TL;DR

**gsm udah solve 14 masalah utama.** Tapi ada **1 critical gap** yang bikin tool ini "incomplete" buat production email use:

> **SPF/DKIM/DMARC missing = email dari 400 domain lo masuk spam.**

Tanpa ini, domain lo "onboarded" tapi email-nya gak deliverable. Itu kayak bikin rumah tapi gak pasang pintu.

**Minimum viable next step:** implement #1 (email auth) + #2 (delete) + #3 (export). Total ~5-6 jam. Setelah itu, gsm genuinely "complete" buat daily ops.
