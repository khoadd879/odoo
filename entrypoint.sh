#!/bin/bash
set -euo pipefail

ADDONS_ROOT="/mnt/extra-addons"
OCA_ROOT="${ADDONS_ROOT}/oca"
CUSTOM_ROOT="${ADDONS_ROOT}/custom"

mkdir -p "${OCA_ROOT}" "${CUSTOM_ROOT}"

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

# env var name per short name (uppercase, dashes → underscores)
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
    echo "[entrypoint] Cloning OCA/${repo} (branch 18.0, sha ${sha})"
    git clone --branch 18.0 --depth 1 "https://github.com/OCA/${repo}.git" "${target}"
    (cd "${target}" && git fetch --depth 1 origin "${sha}" && git checkout "${sha}")
  else
    echo "[entrypoint] Updating OCA/${repo} to sha ${sha}"
    (cd "${target}" && git fetch --depth 1 origin "${sha}" && git checkout "${sha}")
  fi
done

# Symlink each OCA repo's addons/ subdir into the extra-addons root for visibility
for repo_dir in "${OCA_ROOT}"/*/; do
  repo_name=$(basename "${repo_dir}")
  if [[ -d "${repo_dir}/addons" ]]; then
    ln -sfn "${repo_dir}/addons" "${ADDONS_ROOT}/oca-${repo_name}-addons"
  fi
done

echo "[entrypoint] Starting Odoo..."
exec odoo -c /etc/odoo/odoo.conf
