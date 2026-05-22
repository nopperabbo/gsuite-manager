# gsuite-manager (`gsm`)

[![CI](https://github.com/nopperabbo/gsuite-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/nopperabbo/gsuite-manager/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/pypi/pyversions/gsuite-manager?style=flat-square)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/gh/nopperabbo/gsuite-manager/graph/badge.svg)](https://codecov.io/gh/nopperabbo/gsuite-manager)
[![License: MIT](https://img.shields.io/github/license/nopperabbo/gsuite-manager?style=flat-square)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg?style=flat-square)](https://github.com/astral-sh/ruff)
[![Typed: mypy strict](https://img.shields.io/badge/typed-mypy%20strict-blue.svg?style=flat-square)](https://mypy-lang.org/)

**Automate Google Workspace + Cloudflare in one CLI.** Onboard domains, create users, manage DNS — idempotent, tested, production-ready.

```
$ gsm

╭─────────────── gsm - Menu Utama ───────────────╮
│    1. Onboard domains                          │
│    2. Create users (dari file akun.txt)        │
│    3. Create users (auto-generate, tanpa file) │
│    4. Reset password (bulk)                    │
│    5. Suspend users                            │
│    6. Unsuspend users                          │
│    7. Delete users                             │
│    8. Email aliases (add/list/remove)          │
│    9. Groups / mailing list                    │
│   10. Audit: CF vs Workspace gap               │
│   11. Health check DNS                         │
│   12. Check domain expiry                      │
│   13. List domains                             │
│   14. List users                               │
│   15. Inactive user audit                      │
│   16. Apply DNS template                       │
│   17. Move users to OU                         │
│   18. Ledger stats                             │
│   19. Doctor (health check config)             │
│    0. Exit                                     │
╰────────────────────────────────────────────────╯
```

## Why gsuite-manager?

| | Manual (Admin Console + CF Dashboard) | gsuite-manager |
|---|---|---|
| Onboard 10 domains | ~2 hours clicking | `gsm domains add --file domains.txt` → 3 min |
| Create 50 users | Copy-paste hell | `gsm users gen --count 50 --apply` → 30 sec |
| Audit DNS health | Check each domain manually | `gsm health` → instant report |
| Rotate credentials | Remember where everything is | `gsm setup` → guided wizard |

**No SDK to learn. No YAML to write. No API docs to read.** Just `gsm` and pick a number.

## Features

- **Domain onboarding** — Add to Workspace → CF zone → DNS inject → verify (7-step pipeline, idempotent)
- **Auto-disable Email Routing** — Detects CF Email Routing conflict, disables before MX inject
- **DNS propagation fix** — Polls 8.8.8.8 + 1.1.1.1 before verify (eliminates race failures)
- **User management** — Create, delete, suspend, reset password, aliases, groups, OU move
- **Auto-generate users** — Faker-based, locale-aware, collision-safe, with license assignment
- **Audit & monitoring** — CF vs Workspace gap, DNS health, domain expiry alerts
- **Interactive menu** — Just type `gsm`, pick a number. No commands to memorize.
- **Progress bar + ETA** — Real-time progress for batch operations
- **Retry with backoff** — CF API calls retry 3x on transient failures
- **Friendly errors** — Technical errors translated to actionable hints

## Quick Start

```bash
git clone https://github.com/nopperabbo/gsuite-manager.git
cd gsuite-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
gsm setup    # interactive wizard
gsm doctor   # verify 5/5 PASS
gsm          # open menu
```

<details>
<summary><b>Windows / Linux notes</b></summary>

| OS | Activate venv |
|---|---|
| macOS / Linux | `source .venv/bin/activate` |
| Windows CMD | `.venv\Scripts\activate.bat` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |

**macOS Python 3.14:** Run `chflags -R nohidden .venv` after install.

**Linux:** If `venv` missing: `sudo apt install python3-venv`
</details>

## Examples

```bash
# Onboard domains (auto: Workspace + CF + DNS + verify)
gsm domains add --file domains.txt

# Auto-generate 50 users with Education license
gsm users gen --domain school.tech --count 50 --license education --apply

# Audit: what's in CF but not in Workspace?
gsm audit --output gaps.txt

# Reset all passwords in a domain
gsm users reset-password --domain old.tech --random --output new-creds.txt

# One command does everything (auto-detect files in CWD)
gsm go
```

## Prerequisites

- Python 3.11+
- Google Workspace admin account
- Cloudflare account with domains as zones
- [Google OAuth Desktop App credentials](docs/SETUP_GOOGLE_OAUTH.md)
- [Cloudflare API Token](https://dash.cloudflare.com/profile/api-tokens) (template: "Edit zone DNS")

## Documentation

| Doc | Description |
|---|---|
| [Usage Guide (English)](docs/USAGE.md) | Complete command reference |
| [Tutorial (Bahasa Indonesia)](docs/CARA_PAKE.md) | Full usage guide |
| [How to Test](docs/CARA_TEST.md) | Tier 1 smoke + Tier 2 real test |
| [Google OAuth Setup](docs/SETUP_GOOGLE_OAUTH.md) | Get credentials.json step-by-step |
| [CF Token Rotation](docs/QUICK_ROTATE_CF_TOKEN.md) | 3-minute token refresh |
| [Production Runbook](docs/PRODUCTION_RUNBOOK.md) | Pre-production checklist |
| [Roadmap](docs/ROADMAP.md) | Future phases |
| [Changelog](CHANGELOG.md) | Release history |
| [Contributing](CONTRIBUTING.md) | Dev setup & guidelines |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                             │
│  gsm menu │ gsm go │ gsm domains │ gsm users │ gsm groups  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Workflow Layer                            │
│  domain_onboarding (7-step) │ user_bulk_create │ dns_apply  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Client Layer                              │
│  Cloudflare API │ Google Admin SDK │ Google Verify │ DNS     │
│  (retry+backoff)│ (users/domains)  │ (site verify) │(dnspy) │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     Core Layer                               │
│  config (pydantic) │ auth (OAuth2) │ errors │ logging       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   State Layer                                │
│  JSON Ledger (atomic writes, corrupt recovery, archive)     │
└─────────────────────────────────────────────────────────────┘
```

```
src/gsm/
├── cli/         # Typer commands + interactive menu
├── clients/     # CF, Google Admin, Google Verify, DNS, Faker
├── core/        # Config, OAuth, logging, error humanizer
├── models/      # Pydantic schemas (domain, user, results)
├── state/       # JSON ledger (atomic writes, corrupt recovery)
└── workflows/   # Domain onboarding, user creation orchestration
```

## Star History

<a href="https://star-history.com/#nopperabbo/gsuite-manager&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=nopperabbo/gsuite-manager&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=nopperabbo/gsuite-manager&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=nopperabbo/gsuite-manager&type=Date" />
 </picture>
</a>

## License

[MIT](LICENSE) © nopperabbo
