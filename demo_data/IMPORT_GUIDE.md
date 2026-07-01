# IMPORT_GUIDE.md — Steamships Demo Data (SAFE CSV)

Hướng dẫn import thủ công bộ demo data SAFE vào Odoo UI qua Docker Compose. Bộ CSV dành cho prototype Steamships × Odoo (digital transformation demo). Toàn bộ dữ liệu là dữ liệu giả — KHÔNG chạy script tự động import, KHÔNG ghi vào PostgreSQL, KHÔNG gọi XML-RPC/JSON-RPC. Mọi thao tác đều thực hiện qua UI Odoo.

---

## 0. QUAN TRỌNG: chỉ 3 file import chính

Import chính cho demo chỉ gồm **3 file** sau, theo đúng thứ tự:

| # | File | Model |
|---|------|-------|
| 1 | `01_res_partner_clients_SAFE.csv` | `res.partner` |
| 2 | `02_product_template_services_SAFE.csv` | `product.template` |
| 3 | `03_crm_lead_opportunities_SAFE.csv` | `crm.lead` |

Các file còn lại là **reference / optional**:

| File | Trạng thái | Khuyến nghị |
|------|------------|-------------|
| `04_sale_order_demo_quotes_FIXED_OPTIONAL.csv` | optional, risky | Tạo quotation **live trong UI** từ CRM opportunity đã thắng (Won). Tránh lỗi one2many khi import CSV. |
| `05_sale_order_line_demo_quotes_FIXED_OPTIONAL.csv` | optional, risky | Kèm theo file 04, cũng không khuyến nghị import. |
| `06_calendar_demo_events_REFERENCE_ONLY.csv` | reference only | Calendar scene nên demo live bằng **booking link + Google Calendar sync** thay vì import event. |

---

## 1. Chuẩn bị môi trường (Docker)

### 1.1 Kiểm tra tên database trong container

Database mặc định thường là `odoo_dev`. Kiểm tra:

```bash
docker compose exec -T db psql -U odoo -l
```

Nếu tên khác (ví dụ `postgres`, `odoo`, `demo`) thì thay `odoo_dev` trong tất cả lệnh dưới bằng tên đúng.

### 1.2 Backup database + filestore (BẮT BUỘC trước khi import)

```bash
mkdir -p backups

TS=$(date +%Y%m%d_%H%M%S)

docker compose exec -T db pg_dump -U odoo -d odoo_dev -Fc > backups/before_demo_data_$TS.dump

docker compose exec -T odoo tar -C /var/lib/odoo -czf - filestore/odoo_dev > backups/before_demo_data_filestore_$TS.tar.gz

ls -lh backups
```

### 1.3 Kiểm tra backup có đầy đủ

```bash
docker compose exec -T db pg_restore -l < backups/before_demo_data_$TS.dump > /tmp/odoo_backup_check.txt
tar -tzf backups/before_demo_data_filestore_$TS.tar.gz | head
```

Nếu 2 lệnh trên chạy ra output (không lỗi), backup OK.

### 1.4 Bật Developer Mode trong Odoo UI

Settings → General Settings → Developer Tools → **Activate Developer Mode**.

### 1.5 Đảm bảo các module đã cài

`contacts`, `sales`, `crm`, `product`, `calendar`, `base_import`.

### 1.6 Currency PGK

Settings → Accounting → Currencies → kích hoạt **PGK** nếu chưa có.

---

## 2. Thứ tự import

| Bước | File | Menu |
|------|------|------|
| 1 | `01_res_partner_clients_SAFE.csv` | Contacts |
| 2 | `02_product_template_services_SAFE.csv` | Sales → Products |
| 3 | `03_crm_lead_opportunities_SAFE.csv` | CRM → Pipeline |

> Lý do: CRM Leads tham chiếu Customer (Contacts) qua `partner_id/name`. Products phải tồn tại trước khi Sales dùng.

---

## 3. Cách import từng file

### 3.1 Bước 1 — Contacts (10 khách hàng)

1. Mở menu **Contacts**.
2. List view → **Action** (⋮) → **Import records**.
3. **Upload File** → chọn `01_res_partner_clients_SAFE.csv`.
4. Chọn **Create new records**.
5. Mapping các cột CSV → field Odoo:

   | Cột CSV | Field Odoo | Ghi chú |
   |---------|------------|---------|
   | `id` | External ID | `steamships_demo.partner_*` |
   | `name` | Name | |
   | `company_type` | Company Type | value `company` (lowercase) |
   | `email` | Email | |
   | `phone` | Phone | |
   | `mobile` | Mobile | |
   | `street`, `street2` | Street, Street2 | |
   | `city`, `zip` | City, Zip | |
   | `country_id/name` | Country | tên hiển thị đầy đủ `Papua New Guinea` |
   | `category_id/name` | Tags | nhiều tag phân cách bằng dấu phẩy, đã quote trong CSV |
   | `comment` | Internal Notes | |

   **Không có cột `website`** (đã loại bỏ để tránh lỗi Many2one mapping).
6. Kiểm tra preview → bấm **Import**.
7. Sau import, filter Tags = `Demo Client` để thấy 10 record mới.

### 3.2 Bước 2 — Products (15 dịch vụ)

1. Menu **Sales → Products → Products**.
2. **Action → Import records** → Upload `02_product_template_services_SAFE.csv`.
3. **Create new records**.
4. Mapping:

   | Cột CSV | Field Odoo | Ghi chú |
   |---------|------------|---------|
   | `id` | External ID | `steamships_demo.product_*` |
   | `name` | Name | |
   | `default_code` | Internal Reference | |
   | `sale_ok` | Can be Sold | `True` |
   | `detailed_type` | Product Type | `service` |
   | `list_price` | Sales Price | |
   | `standard_price` | Cost | |
   | `description_sale` | Sales Description | |
   | `categ_id/name` | Product Category | tự tạo nếu chưa có |
   | `uom_id/name` | Unit of Measure (Sales) | `Units` |
   | `uom_po_id/name` | Purchase Unit of Measure | `Units` |

   **Đơn vị "per move", "per day", "per night", "per cbm"** được giữ trong `description_sale` — không dùng UoM riêng để tránh lỗi "No matching records found".

5. Kiểm tra: Product Type = `Service` cho mọi dòng, Sales Price không bị swap với Cost.
6. Bấm **Import**.

### 3.3 Bước 3 — CRM Leads (12 opportunities)

1. Menu **CRM → Pipeline**.
2. **Action → Import records** → Upload `03_crm_lead_opportunities_SAFE.csv`.
3. **Create new records**.
4. Mapping:

   | Cột CSV | Field Odoo | Ghi chú |
   |---------|------------|---------|
   | `id` | External ID | `steamships_demo.lead_*` |
   | `name` | Opportunity Name | |
   | `partner_id/name` | Customer | tên phải khớp **chính xác** Contacts đã import |
   | `email_from` | Email | |
   | `phone` | Phone | |
   | `expected_revenue` | Expected Revenue | |
   | `probability` | Probability | 0-100 |
   | `stage_id/name` | Stage | một trong: `Lead Qualified`, `Onboarding Docs`, `Quoted`, `Won`, `Lost` |
   | `description` | Description | |

5. Trước khi import, đảm bảo CRM có đủ 5 stage nêu trên. Nếu thiếu `Lead Qualified`, `Onboarding Docs`, tạo thêm trong CRM Settings → Stages trước.
6. Kiểm tra preview: phải thấy lead `Pacific Cargo PNG Ltd - 20ft Lae to Port Moresby` ở stage `Quoted` (probability = 65).
7. Bấm **Import**.

---

## 4. Test sau import

### 4.1 Contacts
Mở 1 contact, kiểm tra Tags = `Demo Client` + `Shipping`, Country = Papua New Guinea, Phone đúng format.

### 4.2 Products
Filter `Can be Sold = True` → mở `Container FCL 20ft, Lae -> Port Moresby` → Sales Price = 4500, Cost = 3150, Product Type = Service.

### 4.3 CRM Pipeline (Kanban)
Mỗi stage phải có card:
- Lead Qualified: 3
- Onboarding Docs: 3
- Quoted: 3
- Won: 1
- Lost: 2

Lead Pacific phải ở stage `Quoted` với probability 65.

---

## 5. Rollback nếu import sai

### 5.1 Xóa theo External ID

Vào **Settings → Technical → External Identifiers** → filter `Module = steamships_demo` → chọn tất cả → Action → Delete. Sau đó vào từng model xóa records (cascade).

### 5.2 Xóa nhanh theo Tag / Filter

| Model | Cách filter |
|-------|-------------|
| Contacts | Tags = `Demo Client` → Action → Delete |
| Products | Internal Reference starts with `STL-`, `PRP-`, `HSP-`, `JV-` |
| CRM Leads | External ID bắt đầu `steamships_demo.lead_*` |

### 5.3 Restore database từ backup Docker

```bash
docker compose stop odoo

docker compose exec -T db dropdb -U odoo --if-exists odoo_dev
docker compose exec -T db createdb -U odoo odoo_dev
docker compose exec -T db pg_restore -U odoo -d odoo_dev < backups/before_demo_data_YYYYMMDD_HHMMSS.dump

docker compose start odoo
```

### 5.4 Restore filestore từ backup Docker

```bash
docker compose stop odoo

docker compose exec -T odoo rm -rf /var/lib/odoo/filestore/odoo_dev
cat backups/before_demo_data_filestore_YYYYMMDD_HHMMSS.tar.gz | docker compose exec -T odoo tar -C /var/lib/odoo -xzf -

docker compose start odoo
```

---

## 6. Demo scene sau import

Sau khi import 3 file SAFE xong, chạy demo theo các bước:

1. **CRM onboarding:** mở CRM Pipeline Kanban, click lead `Pacific Cargo PNG Ltd - 20ft Lae to Port Moresby`, kéo từ `Quoted` sang `Won` để demo flow chốt đơn.
2. **Sales quote:** từ lead Won bấm **New Quotation**, chọn 1-2 product từ `Sales → Products` (ví dụ `Container FCL 20ft, Lae -> Port Moresby`). **Không** dùng file quote CSV.
3. **Calendar booking:** dùng module `smart_booking` đã có sẵn — vào trang public booking, chọn slot, confirm. Event sẽ sync Google Calendar live.
4. **OCR Bill of Lading:** upload file PDF test (file có sẵn trong `mock_data/` hoặc `chroma_data/`), review fields, approve.

---

## 7. Checklist tổng

- [ ] Backup database + filestore bằng Docker commands
- [ ] Currency PGK kích hoạt
- [ ] Developer Mode bật
- [ ] 5 CRM stage (`Lead Qualified`, `Onboarding Docs`, `Quoted`, `Won`, `Lost`) đã tồn tại
- [ ] Import `01_res_partner_clients_SAFE.csv` (10 partners)
- [ ] Import `02_product_template_services_SAFE.csv` (15 products, UoM = Units)
- [ ] Import `03_crm_lead_opportunities_SAFE.csv` (12 leads, Pacific ở Quoted probability 65)
- [ ] Test Kanban đủ 5 stage
- [ ] Kiểm tra External IDs: Settings → Technical → External Identifiers, filter `steamships_demo`
- [ ] KHÔNG import file 04/05 — tạo quotation live
- [ ] KHÔNG import file 06 — demo calendar bằng booking link

---

## 8. Ghi chú kỹ thuật CSV

- **Encoding:** UTF-8 không BOM.
- **Delimiter:** dấu phẩy `,`. Các ô chứa dấu phẩy trong text đã quote bằng `"`.
- **Số tiền:** không dấu phẩy phân cách hàng nghìn, ví dụ `4500` chứ không phải `4,500`.
- **Email domain:** chỉ dùng `example.com` hoặc `steamships-demo.local`.
- **Phone format:** `+675 7xxx xxxx`.
- **External ID prefix:** tất cả `steamships_demo.*`.
- **UoM:** chỉ dùng `Units` cho tất cả products. Ý nghĩa per-move/per-day được giữ trong description.
- **Không chạy script tự động**, không ghi PostgreSQL, không gọi XML-RPC/JSON-RPC.