#!/bin/bash
# scripts/cli.sh — shortcut to run `odoo` commands inside the container
# Usage: bash scripts/cli.sh <odoo args...>
# Example: bash scripts/cli.sh -d odoo_dev -u hello_shop --stop-after-init
# Example: bash scripts/cli.sh shell -d odoo_dev

set -euo pipefail

docker compose run --rm --entrypoint sh odoo -c "
  envsubst < /etc/odoo/odoo.conf > /tmp/odoo.conf && \
  unset ODOO_RC && \
  odoo -c /tmp/odoo.conf $*
"
