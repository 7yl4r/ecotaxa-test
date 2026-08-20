#!/usr/bin/env bash
# Full rebuild: wipes the DB and all instance data, brings the stack back up
# from scratch, and reloads the synthetic test dataset. This is the "I broke
# something, give me a clean instance" button for frontend dev iteration.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Tearing down (including volumes)..."
docker compose down -v

echo "==> Clearing bind-mounted instance data..."
find vault ftp_area file_srv models eco_users_files -mindepth 1 ! -name '.gitkeep' -exec rm -rf {} + 2>/dev/null || true

./setup.sh
./seed.sh
