#!/usr/bin/env bash
# One-time setup: creates the database, builds the schema, and creates the
# initial administrator account. Safe to re-run (db creation/build steps are
# skipped/no-op'd by postgres/ecotaxa if already done), but if you just want
# to (re)start the stack afterwards use start.sh instead.
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env
set +a

echo "==> Starting the database..."
docker compose up -d pgdb

echo "==> Waiting for postgres to be healthy..."
until [ "$(docker inspect -f '{{.State.Health.Status}}' ecotaxa_pgdb 2>/dev/null)" = "healthy" ]; do
  sleep 2
done

echo "==> Creating the ecotaxa database..."
docker exec -i ecotaxa_pgdb psql -U postgres -h localhost -tc \
  "SELECT 1 FROM pg_database WHERE datname = 'ecotaxa'" | grep -q 1 || \
docker exec -i ecotaxa_pgdb psql -U postgres -h localhost -c \
  "CREATE DATABASE ecotaxa WITH OWNER=postgres ENCODING='UTF8' TEMPLATE=template0 LC_CTYPE='C' LC_COLLATE='C' CONNECTION LIMIT=-1;"

echo "==> Starting the back-end..."
docker compose up -d ecotaxaback
sleep 5

echo "==> Building the database schema..."
docker exec -i ecotaxa_back bash -c "PYTHONPATH=. python cmds/manage.py db build"

echo "==> Applying local schema patches..."
docker exec -i ecotaxa_pgdb psql -U postgres -h localhost -d ecotaxa -c \
  "ALTER TABLE training
     ADD COLUMN IF NOT EXISTS evaluation JSONB,
     ADD COLUMN IF NOT EXISTS model_name VARCHAR(120),
     ADD COLUMN IF NOT EXISTS config JSONB,
     ADD COLUMN IF NOT EXISTS learning_set_size INTEGER;"

echo "==> Setting administrator credentials..."
docker exec -i ecotaxa_pgdb psql -U postgres -h localhost -d ecotaxa -c \
  "UPDATE users SET email='${ADMIN_EMAIL}', password='${ADMIN_PASSWORD}' WHERE id=1;"

echo "==> Starting the full stack..."
docker compose up -d

cat <<EOF

Setup complete.

  URL:      http://localhost:8088
  Login:    ${ADMIN_EMAIL}
  Password: ${ADMIN_PASSWORD}

Change the administrator password after first login.
EOF
