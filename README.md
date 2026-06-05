# Odoo 18.0 Dev Environment

Local Docker-based Odoo 18.0 Community + PostgreSQL 16, with OCA modules and a custom module scaffold.

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
