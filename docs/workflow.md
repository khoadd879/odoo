# Workflow — Odoo 18.0 Dev Environment

Tài liệu giải thích toàn bộ workflow của dự án Odoo 18.0 Docker setup: từ kiến trúc, đến luồng hoạt động, đến các use case thường gặp.

---

## 1. Tổng quan kiến trúc

```
Host (Linux)
└── /home/khoa/Company/odoo/
    ├── docker-compose.yml         ← orchestrate 2 services
    ├── Dockerfile                 ← build custom Odoo image
    ├── entrypoint.sh              ← bootstrap OCA + start Odoo
    ├── odoo.conf                  ← Odoo config (env var placeholders)
    ├── requirements.txt           ← pip deps
    ├── .env                       ← secrets + OCA commits (gitignored)
    ├── .env.example               ← template cho .env
    ├── .gitignore / .dockerignore
    ├── README.md
    ├── docs/
    │   ├── runbook.md             ← operations cheat sheet
    │   ├── workflow.md            ← file này
    │   └── superpowers/           ← design + plan docs
    ├── addons/
    │   ├── oca/                   ← 8 OCA repos, branch 18.0, pinned SHA
    │   │   ├── web/
    │   │   ├── website/
    │   │   ├── sale-workflow/
    │   │   ├── account-financial-tools/
    │   │   ├── stock-logistics-workflow/
    │   │   ├── management-system/
    │   │   ├── server-ux/
    │   │   └── server-tools/
    │   └── custom/                ← module của bạn, extend OCA + core
    │       ├── README.md
    │       └── hello_shop/        ← module scaffold
    │           ├── __init__.py
    │           ├── __manifest__.py
    │           ├── models/
    │           │   ├── __init__.py
    │           │   └── hello_product.py
    │           ├── views/
    │           │   └── hello_product_views.xml
    │           └── security/
    │               └── ir.model.access.csv
    ├── postgres-data/             ← Docker volume, gitignored
    ├── odoo-data/                 ← filestore + sessions, gitignored
    └── scripts/
        ├── init-db.sh             ← idempotent DB creation
        ├── verify-oca.sh          ← audit module install
        ├── smoke.sh               ← HTTP health check
        ├── reset.sh               ← destructive reset
        └── cli.sh                 ← shortcut chạy odoo command

Docker
├── odoo_app    (odoo:18.0, custom build, user root, port 8069/8072)
└── odoo_db     (postgres:16, internal 5432, healthcheck)
```

---

## 2. Luồng khởi động (cold start)

```
User: docker compose up -d
  │
  ├─► docker-compose đọc docker-compose.yml
  │     └─► resolve ${VAR} từ .env (POSTGRES_PASSWORD, ODOO_ADMIN_PASSWD, OCA_*_COMMIT, ports)
  │
  ├─► Service "db" start (postgres:16)
  │     ├─► Tạo user `odoo` + DB `postgres` từ POSTGRES_USER/PASSWORD
  │     ├─► Mount volume postgres-data/ → /var/lib/postgresql/data
  │     └─► Healthcheck: pg_isready mỗi 5s, max 10 retries
  │
  └─► Service "odoo" start (depends_on db: service_healthy)
        │
        ├─► Container chạy entrypoint.sh as root
        │
        ├─► STEP 1: envsubst
        │     odoo.conf có ${ODOO_ADMIN_PASSWD}, ${POSTGRES_PASSWORD}, etc.
        │     entrypoint substitute → /tmp/odoo.conf.rendered
        │     Set ODOO_RC=/tmp/odoo.conf.rendered (override base image default)
        │
        ├─► STEP 2: OCA clone (idempotent)
        │     Với mỗi OCA repo trong entrypoint.sh:
        │       - Nếu SHA = 0000... → skip (warn)
        │       - Nếu /mnt/extra-addons/oca/<repo> chưa tồn tại → git clone --branch 18.0
        │       - Nếu đã tồn tại → git fetch + checkout <SHA>
        │     Tạo symlink oca-<repo>-addons/ → <repo>/addons/
        │
        └─► STEP 3: exec odoo (as root vì container chạy as root)
              - Load addons path: core + custom + 8 OCA repos
              - Đọc ODOO_RC → /tmp/odoo.conf.rendered
              - Kết nối DB: db_host=db, port 5432
              - Start werkzeug HTTP trên :8069
              - Start gevent longpolling trên :8072
```

---

## 3. Luồng HTTP request

```
Browser: GET http://localhost:8069/web/login
  │
  ├─► Docker port mapping: host:8069 → container:8069
  │
  ├─► Odoo werkzeug nhận request
  │     ├─► Check session cookie → session store (/var/lib/odoo/sessions)
  │     └─► Route /web/login → controller
  │
  ├─► Controller render HTML → trả về browser
  │
  └─► (Nếu login POST) → authenticate
        ├─► Query DB: SELECT * FROM res_users WHERE login='admin'
        │     └─► Postgres container: odoo@db:5432, DB odoo_dev
        ├─► Check password (bcrypt)
        └─► Set session cookie → redirect /web
```

---

## 4. Luồng module install / upgrade

### 4.1 Install lần đầu (qua UI hoặc CLI)

```
Qua UI:
  Apps → Update Apps List → search "Hello Shop" → Install
    │
    ├─► Odoo: odoo.modules.loading
    │     ├─► Check depends ['product'] → installed? yes → continue
    │     ├─► Load security/ir.model.access.csv → INSERT INTO ir_model_access
    │     ├─► Load views/hello_product_views.xml → INSERT INTO ir_ui_view
    │     ├─► Execute models/hello_product.py → ALTER TABLE product_template ADD COLUMN hello_tag
    │     └─► Mark state='installed' trong ir_module_module
    │
    └─► Field "Hello Tag" xuất hiện trong form product

Qua CLI:
  bash scripts/cli.sh -d odoo_dev -i hello_shop --stop-after-init
    │
    └─► Tương tự UI flow, Odoo tự shutdown sau khi xong (--stop-after-init)
```

### 4.2 Upgrade sau khi sửa code

```
Dev: edit addons/custom/hello_shop/models/hello_product.py
  │
  ├─► Dev: docker compose restart odoo  (hoặc UI: Upgrade)
  │
  └─► Odoo reload registry:
        ├─► Re-read file → phát hiện thay đổi
        ├─► Re-execute module code (Python)
        ├─► Nếu __manifest__.py data có XML/CSV → re-load
        └─► Field mới (nếu có) được thêm vào model
```

### 4.3 OCA module update

```
Dev: sửa OCA_<REPO>_COMMIT trong .env
  │
  ├─► docker compose restart odoo
  │
  └─► Entrypoint STEP 2 (idempotent):
        - git fetch origin <new SHA>
        - git checkout <new SHA>
        - Odoo reload addons path → module mới/có sửa được load
```

---

## 5. Workflow từng use case

### 5.1 First-time setup (lần đầu clone repo)

```bash
# 1. Lấy code
cd /home/khoa/Company/odoo
git clone <repo> .  # hoặc git pull nếu đã có

# 2. Tạo .env từ template
cp .env.example .env

# 3. Build image Odoo (kèm git, envsubst)
docker compose build

# 4. Start DB
docker compose up -d db

# 5. Tạo DB odoo_dev
bash scripts/init-db.sh

# 6. Install core modules + dependencies
MODULES="website,website_sale,website_blog,website_forum,sale_management,sale,stock,purchase,account,l10n_vn,mass_mailing,mass_mailing_sms"
bash scripts/cli.sh -d odoo_dev -i ${MODULES} --stop-after-init

# 7. Start full stack
docker compose up -d

# 8. Verify
bash scripts/verify-oca.sh    # 102 modules, 0 silent failures
bash scripts/smoke.sh         # HTTP 200

# 9. Login
# http://localhost:8069
# admin / <ODOO_ADMIN_PASSWD trong .env>
```

### 5.2 Daily dev loop (đã setup xong)

```bash
# Morning: start stack
docker compose up -d

# Edit code
vim addons/custom/hello_shop/models/hello_product.py

# Restart Odoo (5-10s)
docker compose restart odoo

# Check logs
docker compose logs odoo --tail=20

# Verify no errors
bash scripts/verify-oca.sh

# Browser
open http://localhost:8069

# Evening: stop stack (giữ data)
docker compose down
```

### 5.3 Tạo custom module mới

```bash
# 1. Tạo skeleton
mkdir -p addons/custom/my_module/{models,views,security,controllers,static}

# 2. Files bắt buộc:
cat > addons/custom/my_module/__init__.py <<EOF
from . import models
from . import controllers
EOF

cat > addons/custom/my_module/__manifest__.py <<EOF
{
    'name': 'My Module',
    'version': '18.0.1.0.0',
    'depends': ['website_sale', 'sale', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/my_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
EOF

# 3. Code
# models/my_model.py
# views/my_views.xml
# security/ir.model.access.csv
# controllers/main.py (nếu có HTTP routes)

# 4. Restart + install
docker compose restart odoo
bash scripts/cli.sh -d odoo_dev -i my_module --stop-after-init

# 5. Verify
bash scripts/verify-oca.sh
```

### 5.4 Reset toàn bộ (mất hết data)

```bash
# Destructive: xóa DB + filestore + custom addons install state
bash scripts/reset.sh --confirm-destructive

# Sau đó: re-setup từ bước 4 của "first-time setup"
bash scripts/init-db.sh
# ... install modules
```

### 5.5 Debug một vấn đề

```bash
# Xem logs Odoo
docker compose logs -f odoo

# Filter errors
docker compose logs odoo 2>&1 | grep -iE "error|warning|cannot be loaded"

# Odoo shell (Python REPL với ORM)
bash scripts/cli.sh shell -d odoo_dev
# Sau đó:
#   env['res.partner'].search([]).mapped('name')
#   env.cr.commit()

# Run unit test
bash scripts/cli.sh -d odoo_test -i my_module --test-enable --stop-after-init --log-level=test

# Inspect DB
docker compose exec -T db psql -U odoo -d odoo_dev
#   \dt              # list tables
#   \d product_template  # describe
#   SELECT * FROM ir_module_module WHERE state='installed';
```

---

## 6. Scripts reference

| Script | Mục đích | Idempotent | Destructive |
|---|---|---|---|
| `init-db.sh` | Tạo DB `odoo_dev` nếu chưa có | ✓ | ✗ (chỉ tạo mới) |
| `verify-oca.sh` | List modules installed, check silent failures | ✓ | ✗ |
| `smoke.sh` | HTTP health check `/web/login`, `/health` | ✓ | ✗ |
| `reset.sh` | Xóa stack + volumes + data dirs | ✗ | ✓ (cần `--confirm-destructive`) |
| `cli.sh` | Wrapper chạy `odoo` command bất kỳ | ✓ | ✗ |

---

## 7. ENV vars reference

| Biến | Mặc định | Mục đích |
|---|---|---|
| `POSTGRES_USER` | `odoo` | Postgres user |
| `POSTGRES_PASSWORD` | (required) | Postgres password |
| `POSTGRES_DB` | `postgres` | Admin DB để tạo DB khác |
| `DB_NAME` | `odoo_dev` | Tên DB Odoo |
| `ODOO_ADMIN_PASSWD` | (required) | Master password cho `/web/database/manager` |
| `ODOO_HTTP_PORT` | `8069` | Host port cho HTTP |
| `ODOO_LONGPOLLING_PORT` | `8072` | Host port cho websocket |
| `ODOO_HTTP_INTERFACE` | `0.0.0.0` | Listen interface |
| `OCA_<NAME>_COMMIT` | 40-char SHA | Pin OCA repo version (branch=18.0) |

OCA repos được track (entrypoint.sh hardcoded): `web`, `website`, `e-commerce`, `sale-workflow`, `account-financial-tools`, `stock-logistics-workflow`, `management-system`, `server-ux`, `server-tools`.

---

## 8. Files đặc biệt — ý nghĩa chi tiết

### `Dockerfile`
- `FROM odoo:18.0` — base Ubuntu noble
- `USER root` — để có quyền trên host-mounted dirs (./addons, ./odoo-data)
- Install `git` (clone OCA), `gettext-base` (envsubst)
- `pip install --break-system-packages` — workaround PEP 668 trên Python 3.12
- `ENTRYPOINT ["/entrypoint.sh"]`

### `entrypoint.sh`
- **STEP 1:** envsubst odoo.conf → /tmp/odoo.conf.rendered; set ODOO_RC
- **STEP 2:** Loop 9 OCA repos, idempotent clone/checkout
- **STEP 3:** Symlink oca-<repo>-addons/
- **STEP 4:** `exec odoo -c /tmp/odoo.conf.rendered`

### `docker-compose.yml`
- `db`: postgres:16, healthcheck, named volume `postgres-data`
- `odoo`: build local, `user: '0:0'`, depends_on db healthy, mount `./addons` và `./odoo-data`
- `restart: unless-stopped` cho cả 2 services

### `odoo.conf`
- Env var placeholders: `${ODOO_ADMIN_PASSWD}`, `${POSTGRES_PASSWORD}`, v.v.
- `addons_path` = core + custom + 8 OCA repos
- `workers = 0` (dev, single process, dễ debug)
- `list_db = True` (dev, cho phép chọn DB)
- `proxy_mode = True` (sẵn sàng cho nginx/TLS sau này)

### `scripts/cli.sh`
- Wrapper duy nhất để gọi `odoo` command
- Tự động: envsubst + unset ODOO_RC + exec odoo
- Dùng: `bash scripts/cli.sh <args>` thay vì nhớ pattern dài

---

## 9. Volumes & persistence

| Path trên host | Mount trong container | Mất khi | Backup |
|---|---|---|---|
| `./postgres-data/` | `/var/lib/postgresql/data` | `docker compose down -v` hoặc `reset.sh` | `pg_dump` |
| `./odoo-data/` | `/var/lib/odoo` | như trên | `tar` (filestore) + `pg_dump` (DB) |
| `./addons/` | `/mnt/extra-addons` | KHÔNG (host fs) | git + clone lại OCA |
| `./addons/custom/` | `/mnt/extra-addons/custom` | KHÔNG | git |
| `.env` | (env vars) | KHÔNG | giữ file backup riêng |

**Quy tắc vàng:** Code + custom modules ở host (git), data ở Docker volume. Reset stack không mất code; reset volumes mất data.

---

## 10. Troubleshooting cheatsheet

| Triệu chứng | Nguyên nhân | Fix |
|---|---|---|
| `Cannot connect to db` | DB chưa ready | `depends_on: service_healthy` (đã có) |
| `option X: invalid integer value: '${VAR}'` | `odoo.conf` chưa envsubst | Dùng `scripts/cli.sh` (đã wrap) hoặc `entrypoint.sh` |
| `Permission denied: /var/lib/odoo/sessions` | Container user không sở hữu host dir | `docker compose exec --user root odoo chown -R 1000:1000 /var/lib/odoo` |
| `Model X is declared but cannot be loaded` | OCA namespace conflict | `DELETE FROM ir_model WHERE model='X';` (xem memory `odoo-payroll-19-patches`) |
| `duplicate key value violates decimal_precision_name_uniq` | OCA + core share name | `DELETE FROM decimal_precision WHERE name='Payroll';` |
| Port 8069 đã dùng | Process khác | `lsof -i :8069` hoặc đổi `ODOO_HTTP_PORT` |
| OCA repo `e-commerce` không có trong `addons/oca/` | Clone fail hoặc bị skip | Check `entrypoint.sh` log, check SHA, re-run |
| Stack Odoo exit ngay sau start | `odoo.conf` syntax lỗi | `docker compose logs odoo` xem lỗi parse |

---

## 11. Bản đồ luồng dữ liệu (data flow)

```
Browser (host)
    │ HTTP
    ▼
host:8069 ──► docker port mapping
    │
    ▼
odoo_app container (port 8069)
    │
    ├── werkzeug HTTP ──► Odoo controller
    │                       │
    │                       ├──► ORM (psycopg2)
    │                       │      │
    │                       │      ▼
    │                       │   postgres:5432
    │                       │      │
    │                       │      ▼
    │                       │   /var/lib/postgresql/data (host: ./postgres-data)
    │                       │
    │                       ├──► Filestore
    │                       │      │
    │                       │      ▼
    │                       │   /var/lib/odoo/filestore (host: ./odoo-data)
    │                       │
    │                       └──► addons path
    │                              │
    │                              ├──► /opt/odoo/addons (core)
    │                              ├──► /mnt/extra-addons/custom (./addons/custom)
    │                              ├──► /mnt/extra-addons/oca/web
    │                              ├──► /mnt/extra-addons/oca/website
    │                              ├──► ... (7 OCA repos)
    │                              └──► symlinks oca-*-addons/
    │
    └── gevent longpolling (port 8072) ──► websocket bus
```

---

## 12. Khi nào dùng cái gì

| Tình huống | Công cụ |
|---|---|
| Edit Python/XML của custom module | VS Code + docker compose restart |
| Test thay đổi | `bash scripts/cli.sh -u <module> --stop-after-init` |
| Xem data, sửa nhanh record | `bash scripts/cli.sh shell -d <db>` |
| Cài module mới | `bash scripts/cli.sh -i <module> --stop-after-init` |
| Debug lỗi UI | Browser DevTools + `docker compose logs -f odoo` |
| Cài OCA module mới | UI: Apps → Update Apps List → Install |
| Update OCA version | Sửa SHA trong `.env` + `docker compose restart odoo` |
| Backup | `docker compose exec -T db pg_dump -U odoo <db> > backup.sql` |
| Reset tất cả | `bash scripts/reset.sh --confirm-destructive` |
| Check stack healthy | `bash scripts/smoke.sh` |
| Audit modules | `bash scripts/verify-oca.sh` |
| Tìm silent load failure | `docker compose logs odoo \| grep -i "cannot be loaded"` |

---

## 13. Tài liệu tham chiếu

- `README.md` — quickstart
- `docs/runbook.md` — operations cheat sheet
- `docs/superpowers/specs/2026-06-05-odoo-18-docker-setup-design.md` — design rationale
- `docs/superpowers/plans/2026-06-05-odoo-18-docker-setup.md` — implementation plan
- OCA repos: https://github.com/OCA (branch 18.0)
- Odoo 18 docs: https://www.odoo.com/documentation/18.0/
- Memory: `odoo-payroll-19-patches` — pattern xử lý OCA conflicts (áp dụng được cho 18.0)
