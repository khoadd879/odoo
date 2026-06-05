#!/bin/bash
set -euo pipefail

if [[ "${1:-}" != "--confirm-destructive" ]]; then
  echo "This will DELETE all data: postgres-data, odoo-data, and any custom addons install state."
  echo "Re-run with: bash scripts/reset.sh --confirm-destructive"
  exit 1
fi

echo "[reset] Stopping stack and removing volumes..."
docker compose down -v

echo "[reset] Removing host-side data dirs..."
rm -rf postgres-data odoo-data

echo "[reset] Done. Run 'bash scripts/init-db.sh' to re-create the DB."
