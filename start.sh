#!/usr/bin/env bash
# Start (or restart) the already-installed stack. Run setup.sh first.
set -euo pipefail
cd "$(dirname "$0")"
docker compose up -d
echo "http://localhost:8088"
