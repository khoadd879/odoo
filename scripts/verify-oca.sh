#!/bin/bash
set -euo pipefail

DB_NAME="${DB_NAME:-odoo_dev}"

echo "Checking for silent module load failures..."
FAILURES=$(docker compose logs odoo 2>&1 | grep -iE "cannot be loaded|duplicate key value" | head -20 || true)
if [[ -n "${FAILURES}" ]]; then
  echo "FAIL: Found silent load failures:"
  echo "${FAILURES}"
  exit 1
fi

echo "Listing installed modules..."
docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d "${DB_NAME}" \
  -c "SELECT name, state FROM ir_module_module WHERE state IN ('installed','to upgrade') ORDER BY name;"

echo "Total installed: $(docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d "${DB_NAME}" -tAc "SELECT count(*) FROM ir_module_module WHERE state='installed'")"
