# Odoo 19.0 Dev Environment

Local Docker-based Odoo 19.0 Community + PostgreSQL 16, with OCA modules and a custom module scaffold.

## Quickstart

```bash
cp .env.example .env
docker compose build
docker compose up -d db
bash scripts/init-db.sh
docker compose up -d
# Open http://localhost:8069 — login admin / <ODOO_ADMIN_PASSWD>
```

See `docs/runbook.md` for common operations.

## Upgrade a custom module

```bash
./scripts/update-module.sh <module_name>
```

Defaults to `DB_NAME=odoo_dev` (override via env). The script runs
`odoo -u <module>` inside the running `odoo` container and exits when done.

## Reset

`scripts/reset.sh` wipes the local dev environment. Always requires
`--confirm-destructive`.

```bash
# Full reset — drops the postgres volume AND removes ./odoo-data (filestore).
bash scripts/reset.sh --confirm-destructive
bash scripts/init-db.sh
docker compose up -d odoo

# Safer reset — drops only the postgres volume.
# Preserves ./odoo-data (Odoo filestore) and ./chroma_data (RAG vector store).
# Use this when you only need a fresh Odoo 19 database (e.g., upgrading
# from an Odoo 18-era DB).
bash scripts/reset.sh --confirm-destructive --db-only
bash scripts/init-db.sh
docker compose up -d odoo
./scripts/update-module.sh steamships_ai
```

Always preserved (regardless of mode): `./addons`, `./custom_addons`,
`./chroma_data`, `./rag`, `./mock_data`, `./docs`, and all config files.
