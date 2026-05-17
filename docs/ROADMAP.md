# Roadmap: Future Phases

> Status saat ini: **Phase 2 complete (public-deliverable, awam-friendly UX)**
> File ini track yang masih bisa ditambahkan, kalo mau scope lebih luas.

---

## Phase 3: Registrar Automation (DEFERRED)

### Konteks

Workflow saat ini mengasumsikan domain udah punya zone di Cloudflare. Buat domain yang baru beli (NS masih di registrar default), `gsm` belum bisa otomatis update NS ke CF.

### Yang dibutuhkan

**Komponen baru:**
- `src/gsm/clients/registrars/` - per-registrar API wrapper
  - `namecheap.py` (REST + IP whitelist)
  - `porkbun.py` (REST + API key)
  - `cloudflare.py` (built-in, paling mudah)
  - `_base.py` - abstract interface (`RegistrarClient` dengan `update_nameservers()`)
- `src/gsm/workflows/full_provision.py` - one-shot: registrar → CF → Workspace
- New CLI: `gsm domains provision <domain>` - end-to-end dari domain baru beli

**Config tambahan:**
- `GSM_REGISTRAR=namecheap|porkbun|cloudflare`
- `GSM_REGISTRAR_API_KEY=...`
- `GSM_REGISTRAR_USER=...` (untuk Namecheap)
- `GSM_REGISTRAR_API_IP=...` (untuk Namecheap whitelist)

**Estimasi effort dengan AI mecut:**
- Single registrar (mis. Porkbun): ~2 jam
- Multiple registrars + abstraction: ~4-5 jam
- Full E2E provision workflow + tests: +2 jam

### Decision saat ini

**DEFERRED** - belum dibutuhkan urgent. Lo (user) memutuskan add nanti pas domain volumenya banyak.

### Workaround manual sementara

Buat domain yang baru beli:

1. Lo manual: login dashboard registrar
2. Update nameservers ke CF (pasti `xxx.ns.cloudflare.com` - dapat dari `gsm` setelah create zone)
3. Tunggu propagasi NS (1-24 jam)
4. Run `gsm domains add <domain>` seperti biasa

`gsm` saat ini udah:
- Auto-create zone di CF kalo belum ada
- Detect existing zone kalo udah ada
- Beri info nameserver CF setelah zone dibuat (di output)

Cuma yang missing: **otomasi update NS di registrar.**

---

## Phase 4: Web GUI (DEFERRED)

### Konteks

CLI cocok buat power user, tapi non-teknis user butuh GUI. Estimasi: 5-6 jam build (FastAPI + HTMX + Tailwind), atau 10 jam untuk Electron desktop app.

### Komponen

- `src/gsm/web/` - FastAPI app
- HTMX-based UI dengan live progress
- Single-password auth (local)
- Optional: Electron wrapper buat desktop app

### Decision saat ini

**DEFERRED** - target audience saat ini adalah power user yang ngerti CLI. Phase 4 dibuka kalo lo butuh distribute ke tim non-teknis.

---

## Phase 5: Concurrent Execution (DEFERRED)

### Konteks

Saat ini sequential dengan delay (anti rate-limit). Buat batch besar (100+ domain), bisa di-parallel-kan dengan worker pool + smart rate limiting.

### Komponen

- Wire `--concurrent N` flag (saat ini gak ada - dihapus karena YAGNI di Phase 1)
- Implementasi `concurrent.futures.ThreadPoolExecutor` di `onboard_domains` + `create_users`
- Token bucket rate limiter per service (CF + Google Admin punya quota berbeda)
- Per-worker progress reporting

### Decision saat ini

**DEFERRED** - sequential dengan `delay=2s` udah cukup buat 150-200 domain (~5-7 menit). Phase 5 dibuka kalo lo onboard 1000+ domain.

---

## Yang BUKAN Roadmap (out of scope)

- ❌ Migrasi DNS records existing dari provider lain ke CF
- ❌ Manage email aliases / groups (di luar user creation)
- ❌ License management (Workspace edition switching)
- ❌ Audit log archival ke S3/GCS
- ❌ Multi-tenant (mengelola banyak Workspace berbeda dari satu instalasi)

Kalo lo butuh salah satu dari ini, kasih tau spesifik - bisa scope-nya cocok jadi Phase tambahan.

---

## Kapan reset roadmap?

Kalo:
- Volume domain tahunan > 500 → consider Phase 5 (concurrent)
- Tim ops/non-tech lebih dari 3 orang yang pake → consider Phase 4 (GUI)
- Beli domain baru tiap minggu → consider Phase 3 (registrar)
