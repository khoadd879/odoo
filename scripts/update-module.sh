#!/bin/bash
#
# Upgrade one Odoo module inside the running `odoo` container.
#
# Usage:
#   ./scripts/update-module.sh <module_name>
#
# Reads DB_NAME from the environment (matches docker-compose / .env).
# Falls back to "odoo_dev" if unset.
#
# Picks the rendered config (/tmp/odoo.conf.rendered) if the container's
# entrypoint has already run envsubst; otherwise falls back to the
# unrendered template at /etc/odoo/odoo.conf.
#
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <module_name>" >&2
  exit 64
fi

MODULE="$1"
DB_NAME="${DB_NAME:-odoo_dev}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: 'docker' not found in PATH." >&2
  exit 127
fi

if ! docker compose ps --status running odoo 2>/dev/null | grep -q odoo; then
  echo "Error: 'odoo' service is not running. Start it with: docker compose up -d odoo" >&2
  exit 1
fi

# Inside the container, prefer the entrypoint-rendered config (envsubst applied).
# Fall back to the template (which still contains ${VAR} placeholders).
ODOO_CONF_PATH="/tmp/odoo.conf.rendered"
if ! docker compose exec -T odoo test -e "${ODOO_CONF_PATH}"; then
  ODOO_CONF_PATH="/etc/odoo/odoo.conf"
fi

echo "[update-module] Upgrading '${MODULE}' on DB '${DB_NAME}' using ${ODOO_CONF_PATH}..."
# -e ODOO_RC= overrides the base image's ENV so Odoo uses ODOO_CONF_PATH via
# the explicit -c flag below instead of the unrendered /etc/odoo/odoo.conf
# template (which still contains literal ${...} placeholders).
exec docker compose exec -T -e ODOO_RC= odoo \
  odoo -c "${ODOO_CONF_PATH}" -d "${DB_NAME}" -u "${MODULE}" --stop-after-init