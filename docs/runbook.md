# Runbook — Odoo 18.0 Dev

## Daily operations

| Task | Command |
|---|---|
| Start stack | `docker compose up -d` |
| Stop stack | `docker compose down` (keeps data) |
| View logs | `docker compose logs -f odoo` |
| Restart after code change | `docker compose restart odoo` |
| Open shell in container | `docker compose exec odoo bash` |
| Reset DB only (keep filestore) | `docker compose down db && docker volume rm $(docker volume ls -q \| grep postgres-data) && docker compose up -d db && bash scripts/init-db.sh` |
| Fix host-mount perms | `docker compose exec --user root odoo chown -R 1000:1000 /mnt/extra-addons /var/lib/odoo` |

## Custom module development

1. Edit code in `addons/custom/<module>/`
2. `docker compose restart odoo`
3. UI: Apps → Update Apps List → Upgrade your module
4. Check logs: `docker compose logs odoo --tail=50`

## OCA module updates

1. Find new commit SHA for repo:
   ```bash
   curl -fsS "https://api.github.com/repos/OCA/<repo>/branches/18.0" \
     | python3 -c 'import json,sys; print(json.load(sys.stdin)["commit"]["sha"])'
   ```
2. Update `OCA_<REPO>_COMMIT` in `.env`
3. `docker compose restart odoo`

## Troubleshooting

### OCA module fails to load with "Model X is declared but cannot be loaded"

Pattern from [[odoo-payroll-19-patches]]. Delete the conflicting `ir_model` row:

```bash
docker compose exec -T db psql -U odoo -d odoo_dev -c \
  "DELETE FROM ir_model WHERE model = 'X';"
docker compose restart odoo
```

### `decimal.precision` duplicate name

```bash
docker compose exec -T db psql -U odoo -d odoo_dev -c \
  "DELETE FROM decimal_precision WHERE name = 'Payroll';"
```

### `option X: invalid integer value: '${VAR}'`

Odoo cannot expand `${VAR}` in `odoo.conf`. The entrypoint runs `envsubst` and points `ODOO_RC` at the rendered file. If you call `odoo` directly (bypassing entrypoint), render first:

```bash
docker compose run --rm --entrypoint sh odoo -c \
  "envsubst < /etc/odoo/odoo.conf > /tmp/odoo.conf && unset ODOO_RC && odoo -c /tmp/odoo.conf -d odoo_dev -i <module> --stop-after-init"
```

### Port 8069 in use

```bash
lsof -i :8069
# Change ODOO_HTTP_PORT in .env, then docker compose up -d
```

### Permission denied on filestore

Container runs as root (`user: '0:0'` in docker-compose). If host files were created with another uid, fix:

```bash
docker compose exec --user root odoo chown -R 1000:1000 /mnt/extra-addons /var/lib/odoo
```

### `--update=all` reports success but `ir_module_module` empty

Silent model load failure. Run:
```bash
docker compose logs odoo 2>&1 | grep -i "cannot be loaded"
```
then fix per [[odoo-payroll-19-patches]] pattern.

### `odoo: command not found` or `gosu: not found`

Rebuild image — `apt-get install` step may have been skipped due to layer cache:

```bash
docker compose build --no-cache
```

## Data model reference

- DB: `postgres-data` Docker volume + local `./postgres-data`
- Filestore: `odoo-data` Docker volume + local `./odoo-data`
- Addons: `./addons` (mounted to `/mnt/extra-addons`)
- OCA source: `./addons/oca/<repo>` (cloned from `branch=18.0`)
- Custom modules: `./addons/custom/<module>`

## First-time setup (from scratch)

```bash
cp .env.example .env
# Edit .env to set POSTGRES_PASSWORD and ODOO_ADMIN_PASSWD (or keep generated)
docker compose build
docker compose up -d db
bash scripts/init-db.sh
# Install core modules:
MODULES="website,website_sale,website_blog,website_forum,sale_management,sale,stock,purchase,account_accountant,account,l10n_vn,mass_mailing,mass_mailing_sms"
docker compose run --rm --entrypoint sh odoo -c \
  "envsubst < /etc/odoo/odoo.conf > /tmp/odoo.conf && unset ODOO_RC && odoo -c /tmp/odoo.conf -d odoo_dev -i ${MODULES} --stop-after-init"
docker compose up -d
# Open http://localhost:8069 — login admin / $ODOO_ADMIN_PASSWD
```
