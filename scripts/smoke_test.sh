#!/usr/bin/env bash
# Smoke test for gsuite-manager: verify install + CLI surface + doctor.
#
# Usage: scripts/smoke_test.sh [--with-real-doctor]
#
# By default runs offline checks only. Pass --with-real-doctor to additionally
# run `gsm doctor` against whatever .env is currently configured.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VENV="$ROOT/.venv"
GSM="$VENV/bin/gsm"

WITH_REAL_DOCTOR=0
if [[ "${1:-}" == "--with-real-doctor" ]]; then
  WITH_REAL_DOCTOR=1
fi

echo "==> Smoke test: gsuite-manager"
echo "    Root: $ROOT"

if [[ ! -x "$GSM" ]]; then
  echo "FAIL: $GSM not executable. Run: ./.venv/bin/python -m pip install -e ."
  exit 1
fi

# macOS Python 3.14 quirk: .venv directory is auto-hidden by macOS Finder,
# which makes Python 3.14 skip .pth files inside (UF_HIDDEN check).
# Strip the hidden flag from the whole venv tree to allow editable install
# to be discovered. No-op on non-macOS.
if command -v chflags >/dev/null 2>&1; then
  chflags -R nohidden "$VENV" 2>/dev/null || true
fi

echo "==> 1. CLI: --help"
"$GSM" --help >/dev/null
echo "    OK"

echo "==> 2. CLI: domains/users subcommands"
"$GSM" domains --help >/dev/null
"$GSM" users --help >/dev/null
"$GSM" doctor --help >/dev/null
"$GSM" init --help >/dev/null
echo "    OK"

echo "==> 3. CLI: init writes .env into temp dir"
TMP="$(mktemp -d)"
"$GSM" init --cwd "$TMP" >/dev/null
test -f "$TMP/.env" || { echo "FAIL: $TMP/.env not created"; exit 1; }
grep -q GSM_CF_API_TOKEN "$TMP/.env" || { echo "FAIL: env template missing GSM_CF_API_TOKEN"; exit 1; }
rm -rf "$TMP"
echo "    OK"

echo "==> 4. Tests + lint + types"
"$VENV/bin/python" -m pytest -q >/dev/null
"$VENV/bin/python" -m ruff check src tests >/dev/null
"$VENV/bin/python" -m mypy src >/dev/null
echo "    OK"

if (( WITH_REAL_DOCTOR )); then
  echo "==> 5. Real gsm doctor (uses current .env)"
  "$GSM" doctor || echo "    (one or more checks failed - inspect above)"
fi

echo
echo "All smoke checks passed."
