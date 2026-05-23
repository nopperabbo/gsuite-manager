# Troubleshooting

Common issues and solutions for gsuite-manager.

## Authentication

### "Token has been expired or revoked"

```bash
rm -f ~/.config/gsm/token.json
gsm setup  # re-authenticate
```

### "The caller does not have permission"

Your Google Workspace account needs **Super Admin** role. Delegated admin won't work for domain/user management APIs.

## DNS

### "MX records not propagated" after domain add

DNS propagation can take 5-60 minutes. gsm polls automatically, but if it times out:

```bash
gsm health --domain example.com  # check current state
gsm domains verify example.com   # retry verification
```

### Cloudflare Email Routing conflict

gsm auto-detects and disables Email Routing before injecting MX records. If you see conflicts:

```bash
# Check CF dashboard → Email → Email Routing → disable
gsm domains add example.com  # retry (idempotent)
```

## Installation

### "No module named gsm"

Ensure you installed in the active venv:

```bash
source .venv/bin/activate
pip install -e .
which gsm  # should point to .venv/bin/gsm
```

### Windows: UnicodeEncodeError

Set terminal to UTF-8:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
```

## State

### Corrupt ledger file

gsm auto-recovers from corrupt JSON entries. If the ledger is completely broken:

```bash
# Backup and reset
cp ~/.config/gsm/ledger.json ~/.config/gsm/ledger.json.bak
echo '{"domains": {}, "users": {}}' > ~/.config/gsm/ledger.json
```

## Getting Help

- [GitHub Discussions](https://github.com/nopperabbo/gsuite-manager/discussions) — Questions & ideas
- [Bug Reports](https://github.com/nopperabbo/gsuite-manager/issues/new?template=bug_report.yml) — File an issue
