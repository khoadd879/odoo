# Odoo 18.0 Docker Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up a reproducible local Odoo 18.0 Community development environment using Docker, with PostgreSQL 16, OCA modules pinned to 18.0, and a scaffolded custom module folder ready for development.

**Architecture:** Custom Dockerfile extends `odoo:18.0` official image; docker-compose orchestrates `db` (postgres:16) + `odoo` services. OCA modules cloned at container start (idempotent, pinned to commit SHA). Custom modules live in host-mounted `addons/custom/`. Hot-reload via `docker compose restart odoo`.

**Tech Stack:** Odoo 18.0 Community, PostgreSQL 16, Docker 29 + Compose v2, Git, OCA 18.0 modules (web, website, e-commerce, sale-workflow, account-financial-tools, stock-logistics-workflow, management-system, server-ux, server-tools), l10n_vn.

---

## File Structure

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrate `db` + `odoo` services |
| `Dockerfile` | Build custom Odoo image with git + OCA support |
| `entrypoint.sh` | Idempotent OCA clone + Odoo start |
| `odoo.conf` | Odoo configuration (db connection, addons path, dev flags) |
| `requirements.txt` | Pip deps (empty by default) |
| `.env.example` | Template for `.env` (secrets + OCA commits) |
| `.gitignore` | Exclude `.env`, `postgres-data/`, `odoo-data/` |
| `.dockerignore` | Exclude volumes/git from build context |
| `scripts/init-db.sh` | Idempotent DB creation |
| `scripts/smoke.sh` | Health check on running stack |
| `scripts/reset.sh` | Destructive reset with confirm |
| `scripts/verify-oca.sh` | Audit `ir_module_module` for silent failures |
| `addons/custom/README.md` | Custom module dev guide |
| `addons/custom/hello_shop/__init__.py` | First custom module — extend `website_sale` |
| `addons/custom/hello_shop/__manifest__.py` | Manifest with explicit depends |
| `addons/custom/hello_shop/models/__init__.py` | Models package init |
| `addons/custom/hello_shop/models/hello_product.py` | Tiny model extending `product.template` |
| `addons/custom/hello_shop/views/hello_product_views.xml` | Add field to product form |
| `addons/custom/hello_shop/security/ir.model.access.csv` | Access rights |
| `docs/runbook.md` | Common operations cheat sheet |

---

## Task 1: Initialize git repo and project skeleton

**Files:**
- Create: `.gitignore`
- Create: `.dockerignore`
- Create: `README.md`

- [ ] **Step 1: Initialize git repo**

```bash
cd /home/khoa/Company/odoo
git init
git config user.email "dev@local"
git config user.name "Local Dev"
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
# Secrets
.env

# Docker volumes
postgres-data/
odoo-data/

# Build artifacts
*.log
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/

# Odoo
*.pyc
*.swp
.venv/

# Editor
.vscode/
.idea/
.DS_Store
```

- [ ] **Step 3: Write `.dockerignore`**

```
.git
.env
postgres-data
odoo-data
docs/superpowers/plans
*.md
!README.md
__pycache__
*.pyc
```

- [ ] **Step 4: Write `README.md`**

```markdown
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
```

- [ ] **Step 5: Initial commit**

```bash
git add .gitignore .dockerignore README.md
git commit -m "chore: initialize project skeleton"
```

---

## Task 2: Write `.env.example` and `requirements.txt`

**Files:**
- Create: `.env.example`
- Create: `requirements.txt`

- [ ] **Step 1: Write `.env.example`**

```bash
# === Required secrets (replace in .env) ===
POSTGRES_PASSWORD=change_me_postgres
ODOO_ADMIN_PASSWD=change_me_admin

# === Database ===
POSTGRES_USER=odoo
POSTGRES_DB=postgres
DB_NAME=odoo_dev

# === OCA repos pinned to commit SHA (18.0 branch) ===
# Find latest SHA per repo at https://github.com/OCA/<repo>/commits/18.0
OCA_WEB_COMMIT=0000000000000000000000000000000000000000
OCA_WEBSITE_COMMIT=0000000000000000000000000000000000000000
OCA_ECOMMERCE_COMMIT=0000000000000000000000000000000000000000
OCA_SALE_WORKFLOW_COMMIT=0000000000000000000000000000000000000000
OCA_ACCOUNT_FINANCIAL_TOOLS_COMMIT=0000000000000000000000000000000000000000
OCA_STOCK_LOGISTICS_WORKFLOW_COMMIT=0000000000000000000000000000000000000000
OCA_MANAGEMENT_SYSTEM_COMMIT=0000000000000000000000000000000000000000
OCA_SERVER_UX_COMMIT=0000000000000000000000000000000000000000
OCA_SERVER_TOOLS_COMMIT=0000000000000000000000000000000000000000

# === HTTP / network ===
ODOO_HTTP_INTERFACE=0.0.0.0
ODOO_HTTP_PORT=8069
ODOO_LONGPOLLING_PORT=8072
```

- [ ] **Step 2: Write `requirements.txt`**

```
# Pin custom Python deps here; leave empty for vanilla Odoo 18.0
```

- [ ] **Step 3: Commit**

```bash
git add .env.example requirements.txt
git commit -m "chore: add .env.example and requirements.txt"
```

---

## Task 3: Write `odoo.conf`

**Files:**
- Create: `odoo.conf`

- [ ] **Step 1: Write `odoo.conf`**

```ini
[options]
admin_passwd = ${ODOO_ADMIN_PASSWD}
db_host = db
db_port = 5432
db_user = ${POSTGRES_USER}
db_password = ${POSTGRES_PASSWORD}
db_name = ${DB_NAME}
data_dir = /var/lib/odoo
addons_path = /opt/odoo/addons,/mnt/extra-addons,/mnt/extra-addons/custom,/mnt/extra-addons/oca/web,/mnt/extra-addons/oca/website,/mnt/extra-addons/oca/e-commerce,/mnt/extra-addons/oca/sale-workflow,/mnt/extra-addons/oca/account-financial-tools,/mnt/extra-addons/oca/stock-logistics-workflow,/mnt/extra-addons/oca/management-system,/mnt/extra-addons/oca/server-ux,/mnt/extra-addons/oca/server-tools
http_interface = ${ODOO_HTTP_INTERFACE}
http_port = ${ODOO_HTTP_PORT}
gevent_port = ${ODOO_LONGPOLLING_PORT}
proxy_mode = True
list_db = True
workers = 0
limit_time_real = 600
limit_memory_hard = 0
log_handler = :INFO
log_level = info
```

- [ ] **Step 2: Commit**

```bash
git add odoo.conf
git commit -m "chore: add odoo.conf with dev defaults"
```

---

## Task 4: Write `Dockerfile` and `entrypoint.sh`

**Files:**
- Create: `Dockerfile`
- Create: `entrypoint.sh`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM odoo:18.0

USER root

# Ensure git is available for OCA cloning
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy Odoo config and entrypoint
COPY odoo.conf /etc/odoo/odoo.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && chown odoo:odoo /etc/odoo/odoo.conf

# Ensure Odoo user owns its data dir
RUN mkdir -p /var/lib/odoo \
    && chown -R odoo:odoo /var/lib/odoo

USER odoo

EXPOSE 8069 8072

ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 2: Write `entrypoint.sh`**

```bash
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
```

- [ ] **Step 3: Make entrypoint executable and commit**

```bash
git add Dockerfile entrypoint.sh
git commit -m "feat: Dockerfile and idempotent OCA entrypoint"
```

---

## Task 5: Write `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    container_name: odoo_db
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-odoo}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-odoo}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  odoo:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: odoo_app
    depends_on:
      db:
        condition: service_healthy
    env_file: .env
    environment:
      # Pass through to odoo.conf via ${VAR} substitution
      ODOO_ADMIN_PASSWD: ${ODOO_ADMIN_PASSWD}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_USER: ${POSTGRES_USER:-odoo}
      DB_NAME: ${DB_NAME:-odoo_dev}
    volumes:
      - ./addons:/mnt/extra-addons
      - ./odoo-data:/var/lib/odoo
    ports:
      - "${ODOO_HTTP_PORT:-8069}:8069"
      - "${ODOO_LONGPOLLING_PORT:-8072}:8072"
    restart: unless-stopped

volumes:
  postgres-data:
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: docker-compose with db + odoo services"
```

---

## Task 6: Set up `.env` and test base build

**Files:**
- Create: `.env` (gitignored)

- [ ] **Step 1: Generate secrets and copy `.env.example` to `.env`**

```bash
cp .env.example .env
# Replace secrets with random values
sed -i "s|change_me_postgres|$(openssl rand -hex 16)|" .env
sed -i "s|change_me_admin|$(openssl rand -hex 16)|" .env
# Verify
grep -E "POSTGRES_PASSWORD|ODOO_ADMIN_PASSWD" .env
```

Expected: two hex strings, neither equals "change_me_*".

- [ ] **Step 2: Resolve real OCA 18.0 commit SHAs and write to `.env`**

```bash
# Helper: resolve HEAD of 18.0 branch for a repo
oca_sha() {
  curl -fsS "https://api.github.com/repos/OCA/$1/branches/18.0" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["commit"]["sha"])'
}

for repo in web website e-commerce sale-workflow account-financial-tools stock-logistics-workflow management-system server-ux server-tools; do
  short=$(echo "$repo" | tr '[:lower:]-' '[:upper:]_')
  sha=$(oca_sha "$repo")
  sed -i "s|^OCA_${short}_COMMIT=.*|OCA_${short}_COMMIT=${sha}|" .env
  echo "OCA/${repo} → ${sha}"
done
```

Expected: 9 lines printed, each with a 40-char hex SHA.

- [ ] **Step 3: Build the image (no commit — `.env` is gitignored)**

```bash
docker compose build 2>&1 | tail -30
```

Expected: build completes, ends with `naming to docker.io/library/odoo-odoo:latest` or similar; no errors.

- [ ] **Step 4: Start the database**

```bash
docker compose up -d db
docker compose ps
```

Expected: `odoo_db` shows status "Up" and "(healthy)".

---

## Task 7: Write `scripts/init-db.sh`

**Files:**
- Create: `scripts/init-db.sh`

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
set -euo pipefail

DB_NAME="${DB_NAME:-odoo_dev}"

# Wait for db to be healthy
echo "Waiting for postgres to be ready..."
for i in {1..30}; do
  if docker compose exec -T db pg_isready -U "${POSTGRES_USER:-odoo}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Check if DB already exists
EXISTS=$(docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")

if [[ "${EXISTS}" == "1" ]]; then
  echo "Database '${DB_NAME}' already exists — skipping init."
  exit 0
fi

echo "Creating database '${DB_NAME}'..."
docker compose run --rm odoo odoo -c /etc/odoo/odoo.conf -d "${DB_NAME}" --init base --stop-after-init

echo "Done. Open http://localhost:8069/web/database/manager to create a fresh DB"
echo "or to start the stack: docker compose up -d"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/init-db.sh
git add scripts/init-db.sh
git commit -m "feat: idempotent init-db script"
```

---

## Task 8: Run `init-db.sh` and verify

**Files:** (no new files; verification step)

- [ ] **Step 1: Run init-db.sh**

```bash
bash scripts/init-db.sh
```

Expected: ends with "Done. Open http://localhost:8069/web/database/manager..."

- [ ] **Step 2: Verify DB exists**

```bash
docker compose exec -T db psql -U odoo -d postgres -c "\l" | grep odoo_dev
```

Expected: line with `odoo_dev | odoo | ...` in the listing.

- [ ] **Step 3: Re-run init-db.sh to confirm idempotency**

```bash
bash scripts/init-db.sh
```

Expected: prints "Database 'odoo_dev' already exists — skipping init." and exits 0.

---

## Task 9: Start stack and smoke test

**Files:** (no new files; smoke test)

- [ ] **Step 1: Start full stack**

```bash
docker compose up -d
sleep 5
docker compose ps
```

Expected: both `odoo_db` and `odoo_app` show "Up". `odoo_app` may briefly show "starting" then "healthy" or "Up" — wait 10s if not ready.

- [ ] **Step 2: Check Odoo logs for OCA clone + module load**

```bash
docker compose logs odoo 2>&1 | tail -30
```

Expected: log contains lines like `[entrypoint] Cloning OCA/web (branch 18.0, sha <sha>)` for each OCA repo, then `Starting Odoo...`, then `odoo.modules.loading: loading XXX modules`.

- [ ] **Step 3: Curl health endpoints**

```bash
curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:8069/web/login
curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:8069/web/database/manager
```

Expected: both return `200`.

- [ ] **Step 4: Open browser and create database via UI**

1. Open `http://localhost:8069/web/database/manager`
2. Master Password = `$ODOO_ADMIN_PASSWD` (from `.env`)
3. New database name: `odoo_dev` (or a new one)
4. Check "Load demonstration data" → leave unchecked for cleaner dev
5. Language: `English` (default), Country: `Vietnam`
6. Click "Continue"
7. Wait for module loading (~2-5 min)

Expected: redirected to `/web` with admin login screen.

---

## Task 10: Install core modules

**Files:** (no new files; install via UI)

- [ ] **Step 1: Install modules in batch**

After login as admin:
1. Open **Apps** menu
2. Click **Update Apps List** (top of screen)
3. Search and install each:
   - `website`
   - `website_sale`
   - `website_blog`
   - `website_forum`
   - `sale_management`
   - `sale`
   - `stock`
   - `purchase`
   - `account_accountant`
   - `account`
   - `l10n_vn`
   - `mass_mailing`
   - `mass_mailing_sms`

Wait for each to finish (~10-30s per module; longer for `account_accountant`).

- [ ] **Step 2: Run OCA audit script**

After installation, run:

```bash
bash scripts/verify-oca.sh
```

(Script created in Task 12 — write a stub now that just lists installed modules.)

For now, list installed modules:

```bash
docker compose exec -T db psql -U odoo -d odoo_dev -c "SELECT name, state FROM ir_module_module WHERE state='installed' ORDER BY name;"
```

Expected: ~50-80 modules listed; the curated list above is present.

- [ ] **Step 3: Verify no silent load failures**

```bash
docker compose logs odoo 2>&1 | grep -iE "cannot be loaded|duplicate key" | head -20
```

Expected: empty output. If non-empty, see Task 14 (Error handling) for fixes.

---

## Task 11: Write `scripts/verify-oca.sh`

**Files:**
- Create: `scripts/verify-oca.sh`

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
set -euo pipefail

DB_NAME="${DB_NAME:-odoo_dev}"

echo "Checking for silent module load failures..."
FAILURES=$(docker compose logs odoo 2>&1 | grep -iE "cannot be loaded|duplicate key value" | head -20 || true)
if [[ -n "${FAILURES}" ]]; then
  echo "FAIL: Found silent load failures:"
  echo "${FAILURES}"
  exit 1
fi

echo "Listing installed modules..."
docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d "${DB_NAME}" \
  -c "SELECT name, state FROM ir_module_module WHERE state IN ('installed','to upgrade') ORDER BY name;"

echo "Total installed: $(docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d "${DB_NAME}" -tAc "SELECT count(*) FROM ir_module_module WHERE state='installed'")"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/verify-oca.sh
git add scripts/verify-oca.sh
git commit -m "feat: verify-oca script for silent load failure detection"
```

---

## Task 12: Write `scripts/smoke.sh`

**Files:**
- Create: `scripts/smoke.sh`

- [ ] **Step 1: Write the script**

```bash
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
```

- [ ] **Step 2: Make executable, run, commit**

```bash
chmod +x scripts/smoke.sh
bash scripts/smoke.sh
git add scripts/smoke.sh
git commit -m "feat: smoke test script"
```

Expected: ends with "[smoke] PASS".

---

## Task 13: Scaffold first custom module `hello_shop`

**Files:**
- Create: `addons/custom/README.md`
- Create: `addons/custom/hello_shop/__init__.py`
- Create: `addons/custom/hello_shop/__manifest__.py`
- Create: `addons/custom/hello_shop/models/__init__.py`
- Create: `addons/custom/hello_shop/models/hello_product.py`
- Create: `addons/custom/hello_shop/views/hello_product_views.xml`
- Create: `addons/custom/hello_shop/security/ir.model.access.csv`

- [ ] **Step 1: Write `addons/custom/README.md`**

```markdown
# Custom Modules

Each subdirectory is an Odoo module. Modules here extend core + OCA; they do not replace them.

## Creating a new module

1. Create `addons/custom/<your_module>/`
2. Add `__init__.py` and `__manifest__.py` (see `hello_shop/` for example)
3. `__manifest__.py` MUST list every dependency in `depends`:
   ```python
   'depends': ['website_sale', 'account', 'sale'],
   ```
4. Code Python models, views, security CSV
5. `docker compose restart odoo`
6. UI: Apps → Update Apps List → search your module → Install

## Iterating

- Python change: `docker compose restart odoo` + Upgrade module
- View XML change: `docker compose restart odoo` + Upgrade module
- Controller change: `docker compose restart odoo` (no Upgrade needed)
- `__manifest__.py` change: `docker compose restart odoo` + Update Apps List

## Dependency matrix

| Custom module | depends on |
|---|---|
| hello_shop | website_sale, product |
| (your module) | ... |
```

- [ ] **Step 2: Write `addons/custom/hello_shop/__init__.py`**

```python
from . import models
```

- [ ] **Step 3: Write `addons/custom/hello_shop/__manifest__.py`**

```python
{
    'name': 'Hello Shop',
    'version': '18.0.1.0.0',
    'summary': 'Scaffold module extending product.template',
    'depends': ['product'],
    'data': [
        'security/ir.model.access.csv',
        'views/hello_product_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'author': 'Local Dev',
    'license': 'LGPL-3',
}
```

- [ ] **Step 4: Write `addons/custom/hello_shop/models/__init__.py`**

```python
from . import hello_product
```

- [ ] **Step 5: Write `addons/custom/hello_shop/models/hello_product.py`**

```python
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hello_tag = fields.Char(
        string='Hello Tag',
        help='Demo field added by hello_shop module to verify custom module install.',
    )
```

- [ ] **Step 6: Write `addons/custom/hello_shop/views/hello_product_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_template_form_view_hello" model="ir.ui.view">
        <field name="name">product.template.form.hello</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product.product_template_form_view"/>
        <field name="arch" type="xml">
            <field name="name" position="after">
                <field name="hello_tag" placeholder="hello"/>
            </field>
        </field>
    </record>
</odoo>
```

- [ ] **Step 7: Write `addons/custom/hello_shop/security/ir.model.access.csv`**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_hello_product_user,hello_product_user,product.model_product_template,base.group_user,1,0,0,0
```

Note: this reuses the existing `product.template` model's access; the `hello_tag` field inherits product.template's ACL.

- [ ] **Step 8: Restart and install via UI**

```bash
docker compose restart odoo
# In UI: Settings → Apps → Update Apps List → search "Hello Shop" → Install
```

Expected: after restart, `Hello Shop` shows in Apps list; clicking Install adds the `Hello Tag` field to product form.

- [ ] **Step 9: Verify field appears**

1. Inventory → Products → open any product
2. Form should show a "Hello Tag" field next to Name

Expected: field visible, save persists.

- [ ] **Step 10: Commit**

```bash
git add addons/custom/
git commit -m "feat: scaffold hello_shop custom module extending product.template"
```

---

## Task 14: Write `scripts/reset.sh` (destructive)

**Files:**
- Create: `scripts/reset.sh`

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
set -euo pipefail

if [[ "${1:-}" != "--confirm-destructive" ]]; then
  echo "This will DELETE all data: postgres-data, odoo-data, and any custom addons install state."
  echo "Re-run with: bash scripts/reset.sh --confirm-destructive"
  exit 1
fi

echo "[reset] Stopping stack and removing volumes..."
docker compose down -v

echo "[reset] Removing host-side data dirs..."
rm -rf postgres-data odoo-data

echo "[reset] Done. Run 'bash scripts/init-db.sh' to re-create the DB."
```

- [ ] **Step 2: Make executable and commit (DO NOT RUN)**

```bash
chmod +x scripts/reset.sh
git add scripts/reset.sh
git commit -m "feat: destructive reset script with explicit confirm flag"
```

---

## Task 15: Write `docs/runbook.md`

**Files:**
- Create: `docs/runbook.md`

- [ ] **Step 1: Write the runbook**

````markdown
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

### Port 8069 in use

```bash
lsof -i :8069
# Change ODOO_HTTP_PORT in .env, then docker compose up -d
```

### Permission denied on filestore

```bash
sudo chown -R 101:101 odoo-data/
```

### `--update=all` reports success but `ir_module_module` empty

Silent model load failure. Run:
```bash
docker compose logs odoo 2>&1 | grep -i "cannot be loaded"
```
then fix per [[odoo-payroll-19-patches]] pattern.

## Data model reference

- DB: `postgres-data` Docker volume + local `./postgres-data`
- Filestore: `odoo-data` Docker volume + local `./odoo-data`
- Addons: `./addons` (mounted to `/mnt/extra-addons`)
- OCA source: `./addons/oca/<repo>` (cloned from `branch=18.0`)
- Custom modules: `./addons/custom/<module>`
````

- [ ] **Step 2: Commit**

```bash
git add docs/runbook.md
git commit -m "docs: operational runbook"
```

---

## Self-Review Checklist

After implementing all tasks, verify:

- [ ] `docker compose up -d` starts both services
- [ ] `http://localhost:8069` loads login page
- [ ] `bash scripts/smoke.sh` exits 0
- [ ] `bash scripts/verify-oca.sh` shows installed modules and reports no silent failures
- [ ] UI can install `Hello Shop` from Apps menu
- [ ] `Inventory → Products → <any product>` shows `Hello Tag` field
- [ ] `bash scripts/reset.sh --confirm-destructive` actually removes data
- [ ] `.env` is in `.gitignore` and `git status` does not show it

## Out-of-Scope Follow-Ups (not in this plan)

- Production deployment (TLS, nginx, monitoring, backups)
- Real custom module business logic
- CI/CD pipeline
- Migration of data from external systems
