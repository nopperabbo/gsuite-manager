# gsuite-manager

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo.svg">
    <img alt="gsuite-manager" src="assets/logo.svg" width="400">
  </picture>
</p>

<p align="center">
  <strong>Automate Google Workspace + Cloudflare in one CLI.</strong><br>
  Onboard domains, create users, manage DNS — idempotent, tested, production-ready.
</p>

---

For full documentation, visit the [Usage Guide](USAGE.md).

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
