# Usage Guide

Complete guide to using gsuite-manager (`gsm`).

## Installation

```bash
git clone https://github.com/nopperabbo/gsuite-manager.git
cd gsuite-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Initial Setup

Run the setup wizard:

```bash
gsm setup
```

This will prompt you for:
- Google OAuth credentials (`credentials.json` path)
- Cloudflare API token
- Default domain (optional)

Verify everything works:

```bash
gsm doctor
```

All 5 checks should show PASS.

## Interactive Menu

Just type `gsm` with no arguments to open the interactive menu:

```bash
gsm
```

Pick a number and follow the prompts. No commands to memorize.

## Commands

### Domain Management

```bash
# Onboard domains (full pipeline: Workspace → CF → DNS → verify)
gsm domains add --file domains.txt

# List all domains
gsm domains list

# Check domain expiry dates
gsm check-expiry

# Apply DNS template to domains
gsm dns-apply --template mx-google.yml --domain example.com
```

### User Management

```bash
# Create users from a file (one email per line)
gsm users add --file akun.txt --domain example.com

# Auto-generate users (Faker-based, locale-aware)
gsm users gen --domain example.com --count 50 --license education --apply

# List users in a domain
gsm users list --domain example.com

# Reset passwords (bulk)
gsm users reset-password --domain example.com --random --output creds.txt

# Suspend/unsuspend users
gsm users suspend --file users.txt
gsm users unsuspend --file users.txt

# Delete users
gsm users delete --file users.txt

# Move users to an organizational unit
gsm users move --domain example.com --ou "/Staff"
```

### Email Aliases

```bash
gsm users alias-add --user john@example.com --alias j@example.com
gsm users alias-list --user john@example.com
gsm users alias-remove --user john@example.com --alias j@example.com
```

### Groups / Mailing Lists

```bash
gsm groups create --email team@example.com --name "Team"
gsm groups list --domain example.com
gsm groups add-member --group team@example.com --member john@example.com
gsm groups remove-member --group team@example.com --member john@example.com
gsm groups members --group team@example.com
```

### Audit & Monitoring

```bash
# Reconcile CF zones vs Workspace domains
gsm audit --output gaps.txt

# DNS health check (MX, TXT, NS records)
gsm health --domain example.com

# Check domain expiry via RDAP
gsm check-expiry

# Inactive user audit
gsm users audit --domain example.com --days 90
```

### All-in-One

```bash
# Auto-detect files in CWD and run everything
gsm go
```

## Flags

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview actions without executing |
| `--json` | Output results as JSON |
| `--verbose` | Show debug logging |
| `--domain` | Target a specific domain |
| `--file` | Input file path |
| `--output` | Output file path |

## Configuration

Config is stored in `~/.config/gsm/config.json` (created by `gsm setup`).

Environment variables (override config):
- `GSM_CF_TOKEN` — Cloudflare API token
- `GSM_GOOGLE_CREDENTIALS` — Path to OAuth credentials.json
- `GSM_DEFAULT_DOMAIN` — Default domain for commands

## Troubleshooting

### `gsm doctor` shows FAIL

| Check | Fix |
|-------|-----|
| Google OAuth | Re-run `gsm setup`, ensure `credentials.json` exists |
| Cloudflare API | Verify token has "Edit zone DNS" permission |
| DNS resolver | Check internet connectivity |
| Config file | Delete `~/.config/gsm/config.json` and re-run `gsm setup` |

### Rate limiting

gsm automatically retries on 429/502/503 errors with exponential backoff (3 attempts). If you're hitting limits consistently, reduce batch sizes or add `--delay` between operations.

### Domain verification stuck

Run `gsm health --domain example.com` to check DNS propagation. Verification requires MX + TXT records to propagate to both 8.8.8.8 and 1.1.1.1.
