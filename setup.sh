#!/usr/bin/env bash
# One-time setup: creates the database, builds the schema, and creates the
# initial administrator account. Safe to re-run (db creation/build steps are
# skipped/no-op'd by postgres/ecotaxa if already done), but if you just want
# to (re)start the stack afterwards use start.sh instead.
set -euo pipefail
cd "$(dirname "$0")"

# Patched service source lives in submodules; make sure they are checked out.
./submodules.sh

# Generate .env on first run. DB_PASSWORD is taken from back_config.ini so the
# pgdb container and the back-end always agree; the admin password is random.
if [ ! -f .env ]; then
  echo "==> No .env found, generating one..."
  db_password=$(sed -n 's/^DB_PASSWORD *= *//p' back_config.ini | tr -d '[:space:]')
  if [ -z "$db_password" ]; then
    echo "ERROR: could not read DB_PASSWORD from back_config.ini" >&2
    exit 1
  fi
  umask 077
  cat > .env <<EOF
DB_PASSWORD=${db_password}
ADMIN_EMAIL=administrator@mail.test
ADMIN_PASSWORD=$(openssl rand -hex 12)
EOF
  umask 022
fi

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

# `db build` creates tables straight from the SQLAlchemy models, i.e. already at
# the latest Alembic revision, but doesn't record that. Stamp a freshly built DB
# so later schema changes (py/cmds/db_upg/versions) apply with `upgrade head`;
# a DB that is already stamped (setup re-run) is just upgraded.
echo "==> Applying schema migrations..."
if docker exec -i ecotaxa_pgdb psql -U postgres -h localhost -d ecotaxa -tc \
     "SELECT to_regclass('public.alembic_version')" | grep -q alembic_version; then
  docker exec -i -w /app/cmds ecotaxa_back bash -c "PYTHONPATH=.. alembic upgrade head"
else
  docker exec -i -w /app/cmds ecotaxa_back bash -c "PYTHONPATH=.. alembic stamp head"
fi

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
