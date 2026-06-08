# Odoo 18.0 Docker Setup — Design

**Date:** 2026-06-05
**Status:** Approved (pending user spec review)
**Owner:** khoa

## Purpose

Local development environment for an Odoo 18.0 Community project, e-commerce focused, with OCA modules as the foundation and a designated folder for custom modules that extend (not replace) OCA + core modules. Stack supports a Vietnamese market site (l10n_vn, VND, VI + EN i18n) but is general enough to cover B2B, B2C, manufacturing, and service flows.

## Scope

**In scope:**
- Docker-based local dev environment (PostgreSQL + Odoo)
- Reproducible OCA module provisioning pinned to 18.0 branch + commit SHA
- Initial database setup with a curated module list
- Hot-reload workflow for custom module development
- Smoke tests and unit test invocation
- Error handling for known OCA-on-18.0 conflicts (memory: [[odoo-payroll-19-patches]])

**Out of scope:**
- Production deployment (HTTPS, monitoring, backups, scale-out)
- Writing the actual custom module business logic
- Migrating existing data from another system
- CI/CD pipelines

## Constraints

- Docker 29.5.2 + Docker Compose 5.1.4 (verified on host)
- Linux host (CachyOS)
- Odoo 18.0 Community (matches user's "OCA + custom" workflow)
- PostgreSQL 16 (compatible with Odoo 18.0; PG 12-16 supported)
- Local dev only — `workers=0`, `list_db=True`, no TLS
- Must work behind a corporate proxy if applicable (env var support)

## Architecture

```
Host (Linux)
├── /home/khoa/Company/odoo/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── odoo.conf
│   ├── requirements.txt
│   ├── entrypoint.sh
│   ├── .env                          (gitignored)
│   ├── .env.example
│   ├── .gitignore
│   ├── .dockerignore
│   ├── addons/
│   │   ├── custom/                   (user-written modules)
│   │   └── oca/                      (git-cloned OCA repos, 18.0 branch)
│   ├── postgres-data/                (gitignored, Docker volume)
│   ├── odoo-data/                    (gitignored, Docker volume)
│   ├── scripts/
│   │   ├── smoke.sh
│   │   ├── init-db.sh
│   │   └── reset.sh
│   └── docs/
│       └── superpowers/specs/
└── Docker
    ├── odoo-app   (port 8069, 8072)
    └── db         (postgres:16, internal only)
```

## Components

### 1. `Dockerfile`

Base image: `odoo:18.0` (official). Layers:
- `apt-get install git` (needed to clone OCA on first start)
- `pip install --no-cache-dir -r /tmp/requirements.txt`
- `COPY odoo.conf /etc/odoo/`
- `COPY entrypoint.sh /entrypoint.sh`
- `RUN chmod +x /entrypoint.sh`
- `EXPOSE 8069 8072`
- Entrypoint: `["bash", "/entrypoint.sh"]`

### 2. `entrypoint.sh`

Idempotent, runs on every container start:
1. `pip install -q -r /tmp/requirements.txt` (no-op if unchanged)
2. For each OCA repo in `$OCA_REPOS`: if `/mnt/extra-addons/oca/<repo>` missing → `git clone --branch 18.0 --depth 1`; else → `git fetch && git reset --hard $COMMIT_SHA`
3. Build `/mnt/extra-addons/` listing: every `addons/` subdirectory under each OCA repo
4. Start Odoo: `exec odoo -c /etc/odoo/odoo.conf`

### 3. `odoo.conf`

Key settings:
- `admin_passwd = $ODOO_ADMIN_PASSWD` (env)
- `db_host = db`, `db_port = 5432`, `db_user = odoo`, `db_password = $DB_PASSWORD`
- `addons_path` = `/opt/odoo/addons,/mnt/extra-addons` plus every `addons/` subdir of OCA repos (computed at build or runtime)
- `data_dir = /var/lib/odoo`
- `workers = 0` (dev)
- `limit_time_real = 600`, `limit_memory_hard = 0`
- `list_db = True` (dev only)
- `proxy_mode = True` (forwarded for nginx / future TLS)
- `log_handler = :INFO`, `log_level = info`

### 4. `docker-compose.yml`

Three services (nginx commented out by default):
- `db`: `postgres:16` image, env `POSTGRES_USER=odoo`, `POSTGRES_PASSWORD`, `POSTGRES_DB=postgres`, volume `postgres-data:/var/lib/postgresql/data`, healthcheck `pg_isready -U odoo`
- `odoo`: build context `.`, depends_on `db` condition `service_healthy`, volumes `./addons:/mnt/extra-addons`, `./odoo-data:/var/lib/odoo`, port `8069:8069`, `8072:8072`, env from `.env`
- `nginx` (optional, profile `tls`): reverse proxy with self-signed cert, X-Forwarded-Proto

### 5. OCA repos pinned to 18.0

The following repos are cloned into `addons/oca/` (branch `18.0`, commit SHA pinned via env):
- `OCA/web` — frontend helpers
- `OCA/website` — website/blog/forum extras
- `OCA/e-commerce` — `website_sale_*` extensions
- `OCA/sale-workflow` — order workflow
- `OCA/account-financial-tools` — accounting extras
- `OCA/stock-logistics-workflow` — inventory workflows
- `OCA/management-system` — multi-flow helpers
- `OCA/server-ux` — backend UX improvements
- `OCA/server-tools` — operational utilities

OCA commit SHAs stored as `OCA_WEB_COMMIT`, `OCA_WEBSITE_COMMIT`, etc. in `.env.example`.

### 6. `addons/custom/`

Each user module is a subdirectory:
```
addons/custom/<module_name>/
├── __init__.py
├── __manifest__.py          (depends on core + OCA modules)
├── models/
├── views/
├── controllers/             (for website extensions)
├── security/
└── static/
```

`__manifest__.py` example for a website_sale extension:
```python
{
    'name': 'Custom Shop Extensions',
    'version': '18.0.1.0.0',
    'depends': ['website_sale', 'account', 'sale'],
    'data': ['security/ir.model.access.csv', 'views/templates.xml'],
    'installable': True,
}
```

### 7. `.env` (gitignored) and `.env.example`

`.env`:
- `POSTGRES_PASSWORD=<random>`
- `ODOO_ADMIN_PASSWD=<random>`
- `OCA_WEB_COMMIT=<sha>`
- `OCA_WEBSITE_COMMIT=<sha>`
- ... (one per OCA repo)

`.env.example` ships with placeholder values and is checked in.

### 8. Scripts

- `scripts/smoke.sh`: `docker compose up -d db`, wait healthy, `docker compose run --rm odoo curl -fsS http://localhost:8069/web/health`, exit code propagates
- `scripts/init-db.sh`: idempotent DB creation — `docker compose run --rm odoo odoo -c /etc/odoo/odoo.conf -d odoo_dev --init base --stop-after-init`; if DB exists, no-op
- `scripts/reset.sh`: stops stack, removes `odoo-data/` and `postgres-data/` after confirmation prompt (DESTRUCTIVE — confirms before deleting)

## Data Flow

```
HTTP request → host:8069 → odoo-app (werkzeug) → addons_path load
  → ORM call → postgres:5432 (db container)
  → filestore read/write → /var/lib/odoo/filestore (odoo-data volume)
  → response
```

Longpolling (websocket bus for chat/notify) → host:8072 → odoo-app Gevent worker.

**Persistence:**
- `postgres-data` volume: DB files, survives `docker compose down` but not `down -v`
- `odoo-data` volume: filestore, sessions, custom-addons install state
- `addons/` directory: source code (Python, XML, JS) — survives container recreate

## Initial Setup Procedure

1. `cp .env.example .env` and edit secrets
2. `docker compose build` (build custom image, ~3-5 min first time)
3. `docker compose up -d db` (start DB first; wait until healthy)
4. `bash scripts/init-db.sh` (creates initial empty DB `odoo_dev` via `odoo --init base --stop-after-init`; idempotent — skips if DB exists)
5. Open `http://localhost:8069/web/database/manager` and create new DB `odoo_dev` (password = `ODOO_ADMIN_PASSWD`) — this second creation step lets you pick installable modules during DB creation (alternative: install via Apps menu after first login)
6. Login as admin → Apps → install:
   - `website`, `website_sale`, `website_blog`, `website_forum`
   - `sale_management`, `sale`
   - `stock`, `purchase`
   - `account_accountant`, `account`
   - `l10n_vn`
   - `mass_mailing`, `mass_mailing_sms`
7. From then on: `docker compose up -d` starts the full stack with DB persisted

## Custom Module Development Workflow

1. Create `addons/custom/<name>/__manifest__.py` with `version = '18.0.1.0.0'`
2. Code in `models/`, `views/`, etc. (on host)
3. `docker compose restart odoo` (~5-10s)
4. UI: Settings → Apps → Update Apps List → search `<name>` → Install / Upgrade
5. Iterate

For controller/template changes only: `docker compose restart odoo` reloads werkzeug.

## Error Handling

| Symptom | Root cause | Fix |
|---|---|---|
| `entrypoint.sh` exits 1 on OCA clone | Network/auth, branch rename, bad SHA | Check `docker compose logs odoo`; verify SHA in `.env`; retry `docker compose up odoo` |
| "Model X is declared but cannot be loaded" | OCA namespace collision (e.g., `hr.payroll.structure` vs Odoo 19 core). Pattern from [[odoo-payroll-19-patches]] | Pre-delete conflicting `ir_model` row, or rename OCA class, or skip module |
| `duplicate key value violates decimal_precision_name_uniq` | OCA + core share `decimal.precision` name | Edit OCA XML to unique name, OR pre-delete row from `decimal_precision` table |
| `psycopg2.OperationalError: connection refused` | DB not ready | `depends_on` healthcheck handles this; if persists, `docker compose restart odoo` |
| `Permission denied` on filestore | UID mismatch (host 1000 vs container 101) | `sudo chown -R 101:101 odoo-data/` |
| Port 8069 in use | Another process | `lsof -i :8069` → kill or change `ports:` mapping |
| Custom module shows "uninstallable" | Missing `__manifest__.py` or bad `depends` | Validate by running `odoo-bin shell -d odoo_dev` and `import_module` |
| `--update=all` reports 0 errors but `ir_module_module` empty | Silent model load failure (memory pattern) | `docker compose logs odoo \| grep -i "cannot be loaded"` |

## Testing

### Smoke test
`scripts/smoke.sh`:
1. Start stack
2. Curl `http://localhost:8069/web/login` → expect HTTP 200
3. Curl `http://localhost:8069/web/health` → expect 200
4. Curl `http://localhost:8069/website/info` → expect 200 (or 404 if not configured; log only)
5. `docker compose down` (keep volumes)
6. Exit 0

### Unit tests
For OCA modules:
```bash
docker compose exec odoo odoo -c /etc/odoo/odoo.conf \
  -d odoo_test --test-enable --stop-after-init \
  -i website_sale_delivery
```

For custom modules:
```bash
docker compose exec odoo odoo -c /etc/odoo/odoo.conf \
  -d odoo_test --test-enable --stop-after-init \
  -u <custom_module_name>
```

### Reproducibility test
`scripts/reset.sh --confirm-destructive`:
1. `docker compose down -v`
2. Remove `postgres-data/`, `odoo-data/`
3. Re-run full setup
4. UI loads, modules installable, no stale rows in `ir_module_module`

## Risks

1. **OCA namespace conflicts on 18.0** — Odoo 18.0 core may have model names that collide with OCA 18.0 modules. Mitigation: `entrypoint.sh` runs `pre-install` script that pre-cleans known conflict rows (extensible).
2. **Custom module must `depends` correctly** — if `depends` includes an uninstalled OCA module, install fails. Mitigation: documented module dependency matrix in `addons/custom/README.md`.
3. **Volume UID drift** — if host UID ≠ 101, permission errors. Mitigation: `entrypoint.sh` runs `chown -R odoo:odoo /var/lib/odoo` on every start.
4. **Memory of patches is for 19.0** — pattern applies to 18.0 but specifics differ. Mitigation: smoke test + `ir_module_module` audit catches silent failures.

## Open Questions

None. All design decisions confirmed via brainstorming.

## Reference

- [[odoo-payroll-19-patches]] — pattern for OCA conflicts (symlink + namespace rename + decimal precision)
- Odoo 18.0 release notes: https://www.odoo.com/page/odoo-18
- OCA 18.0 repos: https://github.com/OCA
