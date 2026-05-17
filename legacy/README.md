# Legacy Scripts

These are the original production scripts that this project replaces. Kept here for reference and as fallback while the new tool is being adopted.

## Files

| Legacy file | New equivalent in `gsm` |
|---|---|
| `gsuite_cloudflare_bot.py` | `gsm domains add --from-file domains.txt` |
| `retry_verify.py` | `gsm domains verify --pending` |
| `create_users.py` | `gsm users add --akun-file akun.txt` |

## Status

These scripts have been **production-tested**:
- 150 domains onboarded via `gsuite_cloudflare_bot.py`
- Hundreds of users created via `create_users.py`
- 271 DNS propagation failures observed in `result_log.txt` (root cause: TXT race - fixed in new `gsm domains add` via `core/dns_check.py`)

## Running Legacy

The legacy scripts still work standalone. They share the same `token.json` and `client_secret_*.json` as the new tool, so OAuth state is interoperable.

```bash
# From the project root
python legacy/gsuite_cloudflare_bot.py
python legacy/retry_verify.py
python legacy/create_users.py
```

## Migration Notes

1. **Hardcoded secrets removed** - new tool reads from `.env`. Old scripts had `CF_API_TOKEN` inline (now rotated).
2. **Path bug fixed** - `create_users.py` resolved `akun.txt` to script's parent directory (`os.path.dirname(SCRIPT_DIR)`). New `gsm users add --akun-file <path>` uses the path you provide directly (CWD-relative).
3. **Idempotency** - new tool tracks state in `gsm_state.json` ledger; legacy scripts re-process everything on each run.
4. **DNS race** - new tool waits for TXT propagation via public resolvers (8.8.8.8, 1.1.1.1) before calling Google verify; legacy did not.

## Removal Plan

Once `gsm` reaches production parity (Phase 1 complete + 2 weeks of stable use), this `legacy/` directory should be removed. Until then it stays as safety net.
