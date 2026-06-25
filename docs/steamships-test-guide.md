# Steamships Demo — Test Guide cho tất cả flow

> Odoo 18 Community · `addons/custom/steamships_demo/` · DB `odoo_dev`
> HTTP: `http://localhost:8069`
> Theo `docs/steamships-plan.md` (4 scenes, 20–25 min demo).

---

## 0. Khởi động nhanh

```bash
# Trạng thái container
docker compose ps

# Nếu Odoo chưa chạy
docker compose up -d odoo
docker compose logs -f odoo --tail=50    # đợi "HTTP service (werkzeug) running on 0.0.0.0:8069"

# URL mở browser
http://localhost:8069/web/login
```

**Login admin** (sau khi `odoo -i base --load-language=vi_VN` / DB mới):
- User: `admin`
- Password: `admin` (DB dev mặc định)

**4 user demo** (seed trong `res_users_data.xml` — dùng để gán sales rep cho lead/booking):

| Login | Tên | Nhóm | Pass mặc định |
|---|---|---|---|
| `sales.lead@steamships.com.pg` | Sales Manager | Sales Manager | `demo` (reset nếu cần) |
| `ship.sales@steamships.com.pg` | Liam (Shipping) | Salesman | `demo` |
| `prop.sales@steamships.com.pg` | Mere (Property) | Salesman | `demo` |
| `hotel.sales@steamships.com.pg` | Aroha (Hotels) | Salesman | `demo` |

> Password được set qua `password='demo'` trong XML. Nếu login fail → `docker compose exec db psql -U odoo -d odoo_dev -c "UPDATE res_users SET password='demo' WHERE login LIKE '%@steamships.com.pg'"`.

**Reset password admin** nếu quên:
```bash
docker compose exec db psql -U odoo -d odoo_dev -c "UPDATE res_users SET password='admin' WHERE login='admin'"
```

---

## 1. Master Data — sanity check (30s)

Mở menu **Steamships → Master Data**:

| Menu | Kỳ vọng |
|---|---|
| Divisions | 3 bản ghi: Shipping & Logistics, Property, Hotels & Hospitality (mở 1 cái → tab Branches có 2-3 chi nhánh) |
| Branches | 6+ bản ghi (Lae, POM, Madang…) |
| Price Lists | 4: Standard PGK, Contract Customer, JV Partner, USD International |
| Customer Onboardings | Trống (sẽ có sau khi submit form) |

**Test nhanh**:
```
Steamships → Master Data → Divisions → "Shipping & Logistics"
→ Tab "Branches" phải có ít nhất 2 chi nhánh (Lae, Port Moresby)
```

---

## 2. Feature 1 — Onboarding (Scene 1, 4 min) ✅

### 2.1 Public form (guest)

Mở **incognito / tab ẩn danh** (không login):

```
http://localhost:8069/onboarding
```

Form có 4 step:
1. Company info (name, country, industry dropdown: Logistics / Property / Hospitality / JV)
2. Contact person (name, email, phone)
3. Service needed + file upload (multi)
4. Notes

Submit → redirect `/onboarding/thanks/<lead_id>` → thấy reference + thông báo.

### 2.2 Verify backend (login admin)

Sau khi submit, kiểm tra:

| Nơi | Kỳ vọng |
|---|---|
| **CRM → Pipeline** (hoặc Steamships menu) | Lead mới xuất hiện ở stage **"Onboarding Docs"** (auto-progress) |
| Lead → tab "Chatter" | Có message: `Onboarding form submitted…` + mail log (nếu SMTP bật) |
| Lead → tab "Extra Info" / Onboarding | Field `Onboarding Status` = `Draft`, `Completion %` = 30% |
| Customer → `res.partner` | Có partner mới với 3 boolean `Registration Form` / `KYC Docs` / `Signed Terms` = False |
| **Mail → Outgoing** (nếu có SMTP) | 1 email "Welcome to Steamships — Reference: …" gửi tới email khách |

### 2.3 Test bằng curl (nhanh)

```bash
curl -X POST http://localhost:8069/onboarding/submit \
  -F "company_name=ACME Mining PNG Ltd" \
  -F "country_code=PG" \
  -F "industry=logistics" \
  -F "contact_name=John Kila" \
  -F "contact_email=john@acme.pg" \
  -F "contact_phone=+675 7123 4567" \
  -F "service_needed=Container shipping FCL 20ft Lae to POM" \
  -F "notes=Monthly contract needed"
```

Response: redirect 303 → `/onboarding/thanks/<id>`. Check CRM pipeline.

### 2.4 KYC Approval flow (admin)

Mở lead vừa tạo → tab chatter → button **"Approve KYC"** (chỉ hiện khi KYC docs đã upload).

Hoặc programmatically:
```
Steamships → Customer Onboardings → chọn record → Action → Approve KYC
```

Sau khi approve:
- Lead stage auto → **"Quoted"**
- Chatter: `KYC approved by Admin`
- Partner booleans: 3/3 = True

---

## 3. Feature 2 — Price List + Quote + Discount Approval (Scene 2, 6 min)

### 3.1 Pricelist setup (1 min)

```
Sales → Products → Pricelists
```

| Pricelist | Giảm giá | Approval |
|---|---|---|
| Standard PGK | 0% | No |
| Contract Customer (10% off) | 10% | No |
| JV Partner (15% off) | 15% | **Yes — Discount Approval** |
| USD International | 0% (USD) | No |

Mở **Standard PGK** → tab "Pricelist Items" → kiểm tra có 20+ products (FCL 20ft, FCL 40ft, Stevedoring, Tug Assist, Office Lease…).

### 3.2 Tạo quotation (1 min)

```
Sales → Quotations → New
```

1. Customer: pick một partner (hoặc tạo mới "Test Client")
2. Pricelist: chọn "JV Partner (15% off)"
3. Add 3 lines:
   - Product: `FCL 20ft Container — Lae to POM`
   - Product: `Stevedoring per move`
   - Product: `Container Terminal Fee`
4. Save

Quotation giá auto-discount 15%. Nếu > 10% → cần approval.

### 3.3 Discount Approval workflow (3 min)

Trên quotation có discount 15%:

1. Click **"Request Approval"** button (header form)
2. Chatter: `Discount approval requested by Admin`
3. Login user **Sales Manager** (`sales.lead@steamships.com.pg`)
4. Mở lại quotation → button **"Approve Discount"** hiện
5. Approve → state chuyển `discount_approved`
6. Quay lại admin → click **"Confirm"** → sale order → CRM opportunity **auto-moves to Won**

### 3.4 Internal margin check (verify)

Trên sale order, tab **"Discount Approval"** → cột **"Internal Margin %"** hiện (computed, không in PDF).

### 3.5 Branded PDF (1 min)

Click **"Print → Quotation / Order"** (hoặc Preview):

- **Header**: navy `#012f5c` + gold line + "STEAMSHIPS" watermark
- **Footer**: navy + gold line + "© 2026 Steamships Trading Company (PNG) Ltd" + page X/Y
- **Body**: logo PNG (nếu có), formatted pricing table, payment terms section

So sánh với Odoo standard PDF (vào Settings → Reports → đổi layout) — branded vs default.

---

## 4. Feature 3 — RAG Chatbot (Scene 2, 6 min) ✅

### 4.1 Mở AI systray (1 min)

Login admin. Góc phải trên cùng (systray) có icon **AI Assistant** (bên cạnh bell notification).

Click icon → modal chat mở. Có 2 tab toggle:
- **Staff mode** (default) — search SOPs + price list + internal policies
- **Client mode** — search onboarding help + FAQ (no prices, no SOPs)

### 4.2 Test staff mode (3 min)

| Câu hỏi | Kỳ vọng |
|---|---|
| "FCL 20ft Lae to POM price?" | Trả lời: PGK price + cite SOP-SHIP-001 + cite Pricelist |
| "What docs needed for container booking?" | Trả lời: list docs + cite SOP-SHIP-004 |
| "Office lease terms for 200m² in POM?" | Trả lời: lease terms + cite SOP-LEASE-002 |
| "What's the cancellation policy for hotel booking?" | Trả lời: cite SOP-HOTEL-001 |
| "Steamships stock price tomorrow?" | Trả lời: "I don't know, please ask Finance team" (prompt forces) |

### 4.3 Test client mode

Click toggle → "Client mode":
- Hỏi "FCL 20ft price?" → refused / no price, redirect to sales rep
- Hỏi "How do I onboard?" → trả lời step-by-step public info

### 4.4 Mock vs Real LLM

Check top of chat modal:
- Nếu thấy badge **(MOCK MODE)** → keyword scoring với 15 SOPs trong `mock_sops.py`.
- Nếu có `GROQ_API_KEY` env → dùng Groq Llama 3.3 70B thật, không có badge.

Set Groq key (optional):
```bash
docker compose stop odoo
# Sửa .env hoặc docker-compose.yml thêm GROQ_API_KEY=...
docker compose up -d odoo
```

Restart Odoo container để env propagate.

### 4.5 Verify chat log persisted

Mở **Steamships → AI Chat History** menu (đã được tạo từ `chat_widget_views.xml`):
- Filter: `[AI Chat` trong body
- Thấy mỗi message lưu + sources

Hoặc query trực tiếp:
```sql
docker compose exec db psql -U odoo -d odoo_dev -c \
  "SELECT id, create_date, question FROM steamships_chatbot_session ORDER BY id DESC LIMIT 5"
```

---

## 5. Feature 4 — B/L Reader (Scene 4, 6 min) ✅

### 5.1 Backend menu (1 min)

```
Steamships → Bills of Lading
```

Có sẵn 5 records seed:
- `PNG-LAE-2026-0001` (95% confidence, pending review)
- `PNG-POM-2026-0042` (88%, pending)
- `PNG-LAE-2026-0117` (72%, pending — LOW CONFIDENCE)
- `PNG-POM-2026-0009` (91%, **approved**)
- `PNG-MDG-2026-0211` (45%, **rejected** — sample reject case)

### 5.2 Test vision extraction (2 min)

Cần upload file ảnh B/L. Module hỗ trợ 2 cách:

**(a) Upload UI trong B/L form**:
1. Mở 1 B/L pending → click **"Upload Scan"** button (header form)
2. Chọn file ảnh (JPG/PNG) → submit
3. Nếu có `GROQ_API_KEY`: Groq Llama 4 Scout trích xuất JSON → điền vào field
4. Nếu mock: stub trả về pre-baked JSON từ filename match

**(b) Curl trực tiếp**:
```bash
# Login trước để lấy session cookie
curl -c cookies.txt -X POST http://localhost:8069/web/session/authenticate \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"login":"admin","password":"admin","db":"odoo_dev"}}'

# Upload + extract
curl -b cookies.txt -X POST http://localhost:8069/steamships/bl/extract \
  -F "file=@/path/to/bl_scan.jpg" \
  -F "create=1"
```

Response: JSON với extracted fields hoặc redirect tới B/L mới.

### 5.3 Test review workflow (2 min)

Mở B/L **`PNG-LAE-2026-0117`** (low confidence 72%):

1. Tab "Chatter" → tab fields
2. Các field có confidence thấp (vd `voyage_number`, `gross_weight_kg`) hiển thị với **badge cảnh báo** (CSS class)
3. Click **"Approve"** → state = `approved` → reviewer_id + reviewed_date set
4. Chatter message: `B/L approved by Admin`

Test reject:
1. Mở B/L pending khác
2. Click **"Reject"** → **PHẢI nhập review_notes** trước (raise `UserError` nếu trống)
3. State = `rejected` → chatter note có reason

### 5.4 Test confidence field decoration

Form view có widget decoration cho field có `confidence < 0.80`:
- Background color: vàng nhạt
- Icon cảnh báo
- Tooltip "Low confidence — please verify"

---

## 6. Feature 5 — Smart Booking (Scene 3, 3 min) ✅

### 6.1 Public booking form (1 min)

Mở incognito:

```
http://localhost:8069/booking
```

4 step wizard:
1. **Type**: Sales Call (30 min) / Client Onboarding (60 min) / Product Demo (60 min)
2. **Date**: dropdown 14 ngày tới
3. **Time slot**: grid 30-min slots 09:00–17:00 PNG time (GMT+10)
4. **Contact**: name, email, phone, preferred host, notes

### 6.2 Submit booking

Click **"Confirm booking"**:
- Redirect `/booking/thanks/<id>`
- Slot state = `confirmed`
- Email confirmation gửi tới email khách (kèm **.ics file** attachment)
- Calendar event tạo (Community `calendar.event` builtin)
- Host (sales rep) thấy trong calendar

### 6.3 Verify backend

Login admin → menu **Steamships → Sales → Appointments**:

| Field | Kỳ vọng |
|---|---|
| Reference | `SS-AP/2026/0001` (sequence) |
| Type | sales_call / onboarding / demo |
| Start datetime | GMT+10 PNG time |
| Duration | 30 hoặc 60 min |
| State | confirmed |
| Host | Liam / Mere / Aroha |
| Calendar event | Có link tới `calendar.event` |

### 6.4 ICS download test

Click **"Download .ics"** trên thank-you page (hoặc trong email):

```
http://localhost:8069/booking/calendar/<token>
```

File ICS mở trong Outlook/Apple Calendar/Google Calendar → event có:
- DTSTART/DTEND in UTC (PNG +10 → UTC)
- SUMMARY: "Steamships — Sales Call"
- ATTENDEE: email khách

### 6.5 Test JSON-RPC API

```bash
# Lấy available slots cho ngày mai
curl -X POST http://localhost:8069/booking/api/available \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"date_from":"2026-06-19","date_to":"2026-06-19","duration":30}}'
```

Response: list slots ISO datetime.

### 6.6 Test conflict prevention

Submit booking slot X. Submit lại slot X (cùng host, cùng time) → 2nd submit fail (validation constraint).

### 6.7 Cron tự động mark done (optional)

Cron `Steamships: Mark past appointments as done` chạy hourly:
- Slot đã confirmed + `end_datetime < now()` → state = `done`

Test manually:
```
Appointments → chọn slot → Action → Mark as Done
```

---

## 7. Branded PDF — quick verify (30s)

In bất kỳ report nào (Quotation, Invoice, B/L):

```
Sale Order → Print → Quotation / Order
```

So sánh **default Odoo PDF** vs **Steamships branded PDF**:
- Background header: navy `#012f5c`
- Bottom border: gold line `#fdd415`
- Watermark: "STEAMSHIPS" top-left
- Footer: navy + copyright + page X/Y

Nếu branded không hiện → kiểm tra:
```bash
docker compose exec odoo ls /mnt/custom/steamships_demo/views/report_header_footer.xml
docker compose exec odoo grep -r "report_steamships_layout" /mnt/custom/steamships_demo/
```

Nếu XML bị lỗi khi upgrade:
```bash
docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d odoo_dev \
  -u steamships_demo --stop-after-init --log-level=warn
```

---

## 8. Cron jobs — verify

Admin → Settings → Technical → Automation → Scheduled Actions:

| Cron | Interval | Model | Code |
|---|---|---|---|
| `Steamships: Cleanup old chatbot sessions` | 1 day | `steamships.chatbot.session` | `model._cron_cleanup_old_sessions(days=90)` |
| `Steamships: Mark past appointments as done` | 1 hour | `steamships.appointment.slot` | `model._cron_mark_past_done()` |

Test manually:
1. Click **"Run Manually"** trên cron
2. Check log: `Steamships: ... ran in X.XXs`

---

## 9. End-to-end Demo Script (theo plan §4 Day 7)

| Scene | Thời gian | Flow |
|---|---|---|
| **Scene 1: Onboarding** | 4 min | Incognito → `/onboarding` → submit → login admin → show CRM pipeline |
| **Scene 2: AI bot + Quote** | 6 min | AI systray → "FCL price?" → answer + sources → switch to Sales → pick pricelist → confirm quote → show discount approval |
| **Scene 3: Booking** | 3 min | Incognito → `/booking` → pick slot → submit → show .ics download → login admin → show appointment in calendar |
| **Scene 4: B/L reader** | 6 min | B/L menu → show 5 records → open low-confidence one → show warning badges → click Approve → show branded PDF |
| **Closing** | 3 min | Phase 2 slide (AI note-taker, AI proposal, AI migration, JV consolidation) |
| **Tổng** | **22 min** | |

---

## 10. Troubleshooting nhanh

| Vấn đề | Cách fix |
|---|---|
| Login fail | `docker compose exec db psql -U odoo -d odoo_dev -c "UPDATE res_users SET password='admin' WHERE login='admin'"` |
| Module không load | `docker compose exec odoo odoo -d odoo_dev -u steamships_demo --stop-after-init` (check log) |
| XML view error | `docker compose logs odoo --tail=100 \| grep -i "view\|xml"` |
| AI không trả lời | Check `GROQ_API_KEY` env; nếu không có thì mock mode chạy |
| Cron không chạy | Settings → Technical → Scheduled Actions → bật `active=True` → "Run Manually" |
| Email không gửi | Settings → Outgoing Mail Servers → cấu hình SMTP. Demo có thể bỏ qua. |
| Port 8069 bận | `docker compose stop odoo` |
| Reset toàn bộ | Xem section 11 dưới |

---

## 11. Reset DB (nuclear option)

```bash
# Stop Odoo
docker compose stop odoo

# Drop DB
docker compose exec db psql -U odoo -d postgres -c "DROP DATABASE odoo_dev"

# Wipe filestore
docker run --rm -v $(pwd)/odoo-data:/data alpine sh -c "rm -rf /data/filestore/*"

# Re-init
docker compose up -d odoo
docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d odoo_dev \
  -i base,crm,sale,sale_management,account,contacts,product,website,calendar,utm,mail,steamships_demo \
  --without-demo=all --stop-after-init

docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d odoo_dev \
  --without-demo=all
```

---

## 12. Test scripts (automated)

```bash
# Full test suite (5 test files, ~20 tests)
docker compose stop odoo
docker compose run --rm -e ODOO_RC= odoo bash -c \
  "unset ODOO_RC && odoo -c /tmp/clean.conf -d odoo_dev -i steamships_demo \
   --test-enable --stop-after-init --test-tags=/steamships_demo \
   --logfile=/tmp/odoo-test.log 2>&1; echo EXIT=\$?"
docker compose up -d odoo

# Xem kết quả
grep -E "FAIL|ERROR|passed|Ran" /tmp/odoo-test.log
```

Test files:
- `tests/test_bill_of_lading.py` (4 tests)
- `tests/test_division.py` (2 tests)
- `tests/test_chatbot.py` (1 test)
- `tests/test_booking.py` (11 tests)
- `tests/test_onboarding.py` (5 tests)

Tổng: **23 tests**.

---

## Tóm tắt 5 features đã implement

| Feature | Plan | Status | Flow test |
|---|---|---|---|
| 1. Onboarding + CRM | ✅ | ✅ Done | Section 2 |
| 2. Price list + Quote | ✅ | ✅ Done | Section 3 |
| 3. RAG Chatbot | ✅ | ✅ Done (Groq + mock) | Section 4 |
| 4. B/L Reader | ✅ | ✅ Done | Section 5 |
| 5. Smart Booking | ✅ | ✅ Done (custom mini-module) | Section 6 |

→ Tất cả **5 features** theo DOCX B6 đã có flow chạy được.
