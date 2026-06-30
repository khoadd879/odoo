#!/bin/bash
set -euo pipefail

# Safe default so envsubst renders a valid odoo.conf even when the host
# .env did not export ODOO_LONGPOLLING_PORT (leaves literal "${...}" in
# gevent_port otherwise, which makes odoo crash on startup).
export ODOO_LONGPOLLING_PORT="${ODOO_LONGPOLLING_PORT:-8072}"
# OCA branch — default to Odoo 19.0 since this prototype targets 19 Community.
# Override in .env: OCA_BRANCH=19.0 (or 18.0 / 17.0 if needed).
export OCA_BRANCH="${OCA_BRANCH:-19.0}"

ADDONS_ROOT="/mnt/extra-addons"
OCA_ROOT="${ADDONS_ROOT}/oca"
CUSTOM_ROOT="${ADDONS_ROOT}/custom"

mkdir -p "${OCA_ROOT}" "${CUSTOM_ROOT}"

# Mark all OCA repos as safe (host-mounted dirs may have mismatched ownership)
git config --global --add safe.directory '*'

# Mapping: short name → GitHub repo
declare -A OCA_REPOS=(
  ["web"]="web"
  ["website"]="website"
  ["e-commerce"]="e-commerce"
  ["sale-workflow"]="sale-workflow"
  ["account-financial-tools"]="account-financial-tools"
  ["stock-logistics-workflow"]="stock-logistics-workflow"
  ["management-system"]="management-system"
  ["server-ux"]="server-ux"
  ["server-tools"]="server-tools"
)

# env var name per short name: uppercase, dashes → underscores
# e.g. "e-commerce" → "OCA_E_COMMERCE_COMMIT" (matches OCA_E_COMMERCE_COMMIT in .env)
#      "sale-workflow" → "OCA_SALE_WORKFLOW_COMMIT"
env_for() {
  echo "OCA_$(echo "$1" | tr '[:lower:]-' '[:upper:]_')_COMMIT"
}

for short in "${!OCA_REPOS[@]}"; do
  repo="${OCA_REPOS[$short]}"
  target="${OCA_ROOT}/${repo}"
  env_name=$(env_for "$short")
  sha="${!env_name:-}"

  if [[ -z "${sha}" || "${sha}" == "0000000000000000000000000000000000000000" ]]; then
    echo "[entrypoint] WARN: ${env_name} not set or zero — skipping OCA/${repo}"
    continue
  fi

  if [[ ! -d "${target}" ]]; then
    echo "[entrypoint] Cloning OCA/${repo} (branch ${OCA_BRANCH}, sha ${sha})"
    git clone --branch "${OCA_BRANCH}" --depth 1 "https://github.com/OCA/${repo}.git" "${target}" || {
      echo "[entrypoint] WARN: clone failed for OCA/${repo}, continuing"
      continue
    }
    (cd "${target}" && git fetch --depth 1 origin "${sha}" && git checkout "${sha}") || \
      echo "[entrypoint] WARN: fetch/checkout failed for OCA/${repo}, keeping clone default"
  else
    echo "[entrypoint] Updating OCA/${repo} to sha ${sha}"
    (cd "${target}" && git fetch --depth 1 origin "${sha}" && git checkout "${sha}") || \
      echo "[entrypoint] WARN: update failed for OCA/${repo}, keeping current checkout"
  fi
done

# Symlink each OCA repo's addons/ subdir into the extra-addons root for visibility
for repo_dir in "${OCA_ROOT}"/*/; do
  repo_name=$(basename "${repo_dir}")
  if [[ -d "${repo_dir}/addons" ]]; then
    ln -sfn "${repo_dir}/addons" "${ADDONS_ROOT}/oca-${repo_name}-addons"
  fi
done

echo "[entrypoint] Substituting env vars in odoo.conf..."
envsubst < /etc/odoo/odoo.conf > /tmp/odoo.conf.rendered
chmod 0644 /tmp/odoo.conf.rendered

# Override ODOO_RC (set by base image) so odoo uses the rendered config
export ODOO_RC=/tmp/odoo.conf.rendered

echo "[entrypoint] Starting Odoo as root (dev only — see docker-compose user: '0:0')..."
exec odoo -c /tmp/odoo.conf.rendered
