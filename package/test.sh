#!/usr/bin/env bash
set -euo pipefail

# ─── Colors ───
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

# Always operate from the package root, regardless of where we were invoked from
cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON=.venv/bin/python

# ─── Virtualenv with the package and its dev extras ───
if [[ ! -x "$PYTHON" ]]; then
    command -v python3 >/dev/null 2>&1 || fail "python3 not found — install Python 3.12+"
    log "Creating .venv ..."
    python3 -m venv .venv
fi

log "Installing flowlab[dev] (editable) ..."
if command -v uv >/dev/null 2>&1; then
    uv pip install --quiet --python "$PYTHON" -e '.[dev]'
else
    "$PYTHON" -m pip --version >/dev/null 2>&1 || "$PYTHON" -m ensurepip --upgrade >/dev/null
    "$PYTHON" -m pip install --quiet -e '.[dev]'
fi

# ─── Lint, type check, test ───
log "ruff ..."
"$PYTHON" -m ruff check src tests

log "mypy ..."
"$PYTHON" -m mypy src

# Extra arguments go straight to pytest, e.g. ./test.sh tests/core -x
# Tests that need a live Postgres, MySQL, Redis, Valkey or Memcached skip themselves.
log "pytest ..."
"$PYTHON" -m pytest "$@"

log "All checks passed."
