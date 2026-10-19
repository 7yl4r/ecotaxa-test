#!/usr/bin/env bash
# (Re)generates the synthetic test dataset and imports it into a fresh
# "Seed Test Dataset" project. Safe to re-run: it deletes the previous
# run's project first and rebuilds deterministically (same random seed).
#
# Requires the stack to already be up (./setup.sh or ./start.sh) and the
# administrator account to exist.
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env
set +a

VENV=.venv-seed
# The venv counts as ready only once its requirements installed (marker file),
# so a half-built venv from an interrupted or failed run is rebuilt, not reused.
if ! cmp -s seed/requirements.txt "$VENV/.requirements-installed" 2>/dev/null; then
  echo "==> Creating $VENV..."
  rm -rf "$VENV"
  if ! python3 -m venv "$VENV" 2>/dev/null; then
    # Some distro Pythons ship without ensurepip (Debian/Ubuntu: python3.X-venv
    # not installed). Build the venv without pip and bootstrap pip instead.
    rm -rf "$VENV"
    python3 -m venv --without-pip "$VENV"
    curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$VENV/bin/python" - --quiet
  fi
  "$VENV/bin/python" -m pip install --quiet -r seed/requirements.txt
  cp seed/requirements.txt "$VENV/.requirements-installed"
fi

"$VENV/bin/python" seed/generate_dataset.py
"$VENV/bin/python" seed/import_dataset.py

echo "  Login:    ${ADMIN_EMAIL} (password: ADMIN_PASSWORD in .env)"
