#!/bin/bash
#
# Reset the Odoo development environment.
#
# Usage:
#   bash scripts/reset.sh --confirm-destructive           # full reset (destructive)
#   bash scripts/reset.sh --confirm-destructive --db-only # drop only the postgres
#                                                         # volume; keep filestore
#                                                         # and RAG vector store
#
# Always preserved (regardless of flags):
#   ./addons, ./custom_addons, ./chroma_data, ./rag,
#   ./mock_data, ./docs, .env, docker-compose.yml, Dockerfile, odoo.conf, scripts/
#
set -euo pipefail

if [[ "${1:-}" != "--confirm-destructive" ]]; then
  echo "Usage: bash scripts/reset.sh --confirm-destructive [--db-only]" >&2
  echo "  --db-only   Drop only the postgres volume; keep ./odoo-data and ./chroma_data." >&2
  exit 1
fi
shift

DB_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --db-only) DB_ONLY=1 ;;
    *) echo "Unknown flag: $arg" >&2; exit 64 ;;
  esac
done

echo "[reset] Will DELETE:"
if [[ "$DB_ONLY" -eq 1 ]]; then
  echo "  - the postgres Docker named volume (postgres-data) declared in docker-compose.yml"
else
  echo "  - the postgres Docker named volume (postgres-data)"
  echo "  - the host bind-mount ./odoo-data (Odoo filestore)"
fi
echo "[reset] Will PRESERVE:"
echo "  - ./addons, ./custom_addons            (addon source on host)"
echo "  - ./chroma_data                        (RAG vector store)"
echo "  - ./rag, ./mock_data, ./docs           (source and docs)"
echo "  - .env, docker-compose.yml, Dockerfile, odoo.conf, scripts/"

if [[ "$DB_ONLY" -eq 1 ]]; then
  echo "[reset] --db-only: stopping odoo service..."
  docker compose stop odoo || true

  echo "[reset] --db-only: removing db container and its named volume (preserving ./odoo-data and ./chroma_data)..."
  # `docker compose down -v` removes ONLY the named volumes declared in
  # docker-compose.yml. Bind-mounts (./odoo-data, ./chroma_data) are never
  # touched by -v, so they survive this step.
  docker compose down -v db

  echo "[reset] --db-only: starting fresh empty postgres..."
  docker compose up -d db

  echo "[reset] --db-only: done. Next steps:"
  echo "  bash scripts/init-db.sh"
  echo "  docker compose up -d odoo"
  echo "  ./scripts/update-module.sh steamships_ai"
  exit 0
fi

# --- Full destructive reset (original behavior) ---
echo "[reset] Stopping stack and removing volumes..."
docker compose down -v

echo "[reset] Removing host-side data dirs..."
rm -rf postgres-data odoo-data

echo "[reset] Done. Run 'bash scripts/init-db.sh' to re-create the DB."