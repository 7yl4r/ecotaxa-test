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
if [ ! -d "$VENV" ]; then
  echo "==> Creating $VENV..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet -r seed/requirements.txt
fi

"$VENV/bin/python" seed/generate_dataset.py
"$VENV/bin/python" seed/import_dataset.py
