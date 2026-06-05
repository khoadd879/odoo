#!/bin/bash
set -euo pipefail

DB_NAME="${DB_NAME:-odoo_dev}"

# Wait for db to be healthy
echo "Waiting for postgres to be ready..."
for i in {1..30}; do
  if docker compose exec -T db pg_isready -U "${POSTGRES_USER:-odoo}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Check if DB already exists
EXISTS=$(docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")

if [[ "${EXISTS}" == "1" ]]; then
  echo "Database '${DB_NAME}' already exists — skipping init."
  exit 0
fi

echo "Creating database '${DB_NAME}'..."
# Bypass entrypoint; render odoo.conf with envsubst, then init base
docker compose run --rm \
  --entrypoint "sh" \
  odoo \
  -c "envsubst < /etc/odoo/odoo.conf > /tmp/odoo.conf && unset ODOO_RC && odoo -c /tmp/odoo.conf -d ${DB_NAME} --init base --stop-after-init"

echo "Done. Open http://localhost:8069/web/database/manager to create a fresh DB"
echo "or to start the stack: docker compose up -d"
