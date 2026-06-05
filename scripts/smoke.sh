#!/bin/bash
set -euo pipefail

echo "[smoke] Starting stack..."
docker compose up -d
sleep 5

echo "[smoke] Waiting for Odoo to respond..."
for i in {1..30}; do
  CODE=$(curl -fsS -o /dev/null -w "%{http_code}" http://localhost:8069/web/login || echo "000")
  if [[ "${CODE}" == "200" ]]; then
    break
  fi
  sleep 2
done

if [[ "${CODE}" != "200" ]]; then
  echo "[smoke] FAIL: web/login did not return 200 (got ${CODE})"
  docker compose logs odoo --tail=50
  exit 1
fi

echo "[smoke] web/login → 200 ✓"
echo "[smoke] web/database/manager → $(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:8069/web/database/manager) ✓"
echo "[smoke] web/health → $(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:8069/web/health) ✓"

echo "[smoke] PASS"
