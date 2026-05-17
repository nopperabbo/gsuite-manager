# Production Setup Runbook

Step-by-step actions the user must perform before running `gsm` against real
Workspace + Cloudflare resources. This document is consumed by the human
operator; the CLI cannot perform these steps because they require browser
authentication and physical credential issuance.

---

## Step 1 — Rotate Cloudflare API token

**Why:** the legacy token shipped in `legacy/gsuite_cloudflare_bot.py` was
committed to source control and is shown as `Invalid API Token` by
`gsm doctor`. Any token that ever lived in a repo or chat must be considered
compromised.

**Required scopes:**

| Permission group | Scope | Resource |
|---|---|---|
| Account | Cloudflare Tunnel: Read (optional) | All accounts (or specific) |
| Zone | Zone: Edit | All zones (or specific) |
| Zone | DNS: Edit | All zones (or specific) |

**Procedure:**

1. Open https://dash.cloudflare.com/profile/api-tokens in a browser.
2. Click **Create Token**.
3. Use the **Edit zone DNS** template OR custom token with scopes above.
4. Under **Account Resources**, scope to your account (account ID
   `0061a056f8cbc860fb9ec99bd41a0ccc` per current config).
5. Under **Zone Resources**, choose `Include - All zones from an account` for
   the same account.
6. Click **Continue to summary** → **Create Token**.
7. **Copy the token immediately** (Cloudflare only shows it once).
8. Edit `.env` in the project root:

   ```bash
   GSM_CF_API_TOKEN=<paste_new_token_here>
   ```

9. Verify:

   ```bash
   gsm doctor
   ```

   The `cloudflare` row should now show `PASS`.

10. **Revoke the old token** at the same URL: find the token whose first chars
    match `Qh1dr2J1...`, click **Roll**, confirm.

---

## Step 2 — (Optional) Rotate Google OAuth Desktop App client secret

**Why:** the `client_secret_*.json` for the OAuth Desktop App was committed and
should be considered compromised. Lower priority than CF because Desktop App
secrets are not cryptographic secrets in the strict sense (Google docs even
note they may be shipped with installed apps), but rotation is good hygiene.

**Procedure:**

1. Open https://console.cloud.google.com/apis/credentials in the project that
   issued the current OAuth client.
2. Find the Desktop App OAuth 2.0 Client ID matching the local
   `client_secret_*.json`.
3. Click the trash icon to **delete** the old client (or click the entry and
   then **Reset Secret** if your Cloud project supports it).
4. Click **Create Credentials → OAuth client ID → Desktop app**.
5. Download the JSON file. Save it as `credentials.json` in the project root
   (or wherever `GSM_GOOGLE_OAUTH_CLIENT_PATH` points).
6. Delete `token.json` (forces re-auth on next run):

   ```bash
   rm token.json
   ```

7. Run any `gsm` command that needs auth (e.g. `gsm domains add example.com`).
   A browser window will open for re-authentication.
8. Verify scopes were granted: token.json now exists and `gsm doctor` passes
   the `oauth_client` row.

---

## Step 3 — Run a real fresh-domain smoke test

**Why:** unit tests cover all branches with mocks, but only a real run
validates that the integrated pipeline (Workspace → CF → DNS injection →
propagation poll → Google verify) actually completes against production APIs.

**Pre-conditions:**

- Step 1 (CF token) complete.
- Step 2 OR existing valid `token.json` working.
- A test domain you own and have not yet onboarded (or are willing to
  re-onboard).
- The domain's registrar nameserver edit page open (for the next step).

**Procedure:**

```bash
# 1. Run the onboarding (idempotent - safe to retry)
gsm domains add my-test-domain.example

# Watch the output. Expected sequence:
#   step_add_gsuite        - registers domain in Workspace
#   step_fetch_token       - gets DNS_TXT verification token from Google
#   step_ensure_zone       - creates CF zone, prints nameservers
#   step_inject_dns        - upserts 5 MX records + 1 TXT
#   step_wait_dns          - polls 8.8.8.8 + 1.1.1.1 until TXT visible
#   step_verify            - tells Google to verify via DNS_TXT

# If `step_wait_dns` reports `propagated=False`:
#   This is the historical 271-failure scenario. The workflow now correctly
#   marks the domain as DNS_PENDING instead of failing verify_domain.
#   Action: copy the CF nameservers from earlier output, paste them at your
#   registrar, wait 5-10 minutes, then:
gsm domains verify --only-pending

# 2. Inspect ledger state
gsm domains list

# 3. Re-running the same command should be a no-op (idempotency check)
gsm domains add my-test-domain.example
# Expect: "skipped (already verified)"
```

**Pass criteria:**

- Final status `VERIFIED` in `gsm domains list`
- Ledger file `gsm_state.json` contains the domain with full history
- Re-running `gsm domains add` returns `skipped`
- No exceptions, no `[-]` lines in the log output

---

## Step 4 — Bulk user creation smoke test

**Pre-conditions:**

- At least one domain in `VERIFIED` state from Step 3.
- An `akun.txt` file with at least 2 test users using that domain.

**Procedure:**

```bash
# Format of akun.txt:
#   firstuser@verified-domain.example | TempPassword123! | optional-code
#   second.user@verified-domain.example | OtherPassword456!

gsm users add --file akun.txt
gsm users list
```

**Pass criteria:**

- All users show status `CREATED`
- Re-running with the same file returns `skipped` for each (idempotency)
