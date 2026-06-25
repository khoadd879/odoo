# Steamships System Audit — Thiếu gì, Cần gì

> Date: 2026-06-15
> Source: DOCX `steamships-plan.docx` (June 2026) + code thật trong `addons/custom/steamships_demo/`
> Scope: toàn bộ 5 features, không chỉ AI
> Status: **cần thêm ~60% để demo được**

---

## 1. Snapshot hệ thống hiện tại (đo thật từ DB)

| Entity | Count | Source |
|--------|-------|--------|
| `ir_module_module` (steamships_demo) | 1, **installed** ✅ | psql |
| `product.template` (active) | 12 | psql |
| `product.pricelist` | 5 | psql |
| `crm.team` | 7 (4 Steamships + 3 Odoo default) | psql |
| `crm.lead` | 5 demo leads | psql |
| `res.currency` (PGK + USD) | 2 active | psql |
| `res.partner` (customer) | **0** ❌ | psql (có 4 partners nhưng `customer_rank=0`) |
| `crm.stage` (custom 5 stages) | ❌ chưa có | chỉ dùng Odoo default |
| `mail.activity` (24h follow-up) | ❌ chưa có | chưa auto-create |
| `ir.attachment` (B/L scans) | ❌ 0 | chưa có |
| `account.move` (Bills) | ❌ 0 | chưa test invoice OCR |
| `calendar.event` (booking) | ❌ 0 | chưa có |
| `appointment.type` | ❌ 0 | chưa install Enterprise appointment |

**Code structure** (audit filesystem):
- 6 models: `division`, `branch`, `crm_lead_onboarding`, `crm_lead_link`, `sale_order_approval`
- 1 controller: `ai_chatbot` (G1+G2 done — mock mode, 2-mode toggle)
- 1 wizard: `crm_lead_onboarding_wizard`
- 11 data XML files
- 1 JS asset: `chat_widget.esm.js` (backend client action)
- 7 view XML files

**Không có**:
- `middleware/` (FastAPI service)
- `models/bill_of_lading.py`
- `models/bill_of_lading_field.py`
- `wizards/ocr_wizard.py`
- `data/sop_documents.xml` (chỉ có mock_sops.py in-code)
- `data/sample_bls/` (5 B/L scans)

---

## 2. Feature-by-feature audit

### Feature 1 — CRM + Onboarding (Scene 1, 4 min)

**Có gì** (✅):
- `steamships.division` (4 divisions: SHIP, PROP, HOTL, LOGI)
- `steamships.branch` (4 branches: POM, Lae, Motukea, Daru)
- `crm.lead.steamships.onboarding` (KYC 8 items + completion_pct compute)
- `crm.lead` inherits → onboarding_id related + KYC stat button
- 5 demo leads (1 per division) với real PNG partners (Marienburg Mining, Ok Tedi, BSP, AHC)
- 4 CRM teams (Shipping, Property, Hotels, Logistics) với invoiced_target

**Thiếu gì** (❌):

| # | Gap | DOCX ref | Effort | Priority |
|---|-----|----------|--------|----------|
| F1.1 | **Web onboarding form** — `/onboarding` public page với fields chuẩn DOCX (industry 4 options, service_needed multi-select) | B2 | 2h | 🔴 P0 |
| F1.2 | **Auto-create lead** từ form submit (controller hook vào form builder) | B2 | 1h | 🔴 P0 |
| F1.3 | **Auto-assign salesperson** (round-robin rule) | B2 | 30min | 🔴 P0 |
| F1.4 | **24h mail.activity** auto-create khi lead mới | B2 | 30min | 🔴 P0 |
| F1.5 | **5 pipeline stages** (Lead → Qualified → Onboarding Docs → Quoted → Won/Lost) — hiện dùng Odoo default | B2 | 30min | 🟡 P1 |
| F1.6 | **Fix industry selection** (8 options hiện tại → 4 options DOCX: Logistics/Property/Hospitality/JV) | B2 | 15min | 🟡 P1 |
| F1.7 | **`service_needed` field** (multi-select) trên onboarding model | B2 | 30min | 🟡 P1 |
| F1.8 | **Stage auto-transition** khi KYC approved → lead stage = "Quoted" | B2 implicit | 1h | 🟡 P1 |
| F1.9 | **Partners cần `customer_rank > 0`** để hiện trong dropdown khi tạo quotation | — | 15min | 🟡 P1 |
| F1.10 | **Thêm 2 branches**: Madang, Rabaul (DOCX C4 yêu cầu real PNG route names) | C4 | 15min | 🟢 P2 |

**Demo impact nếu thiếu**: Scene 1 workaround — tạo lead thủ công từ backend, bỏ qua "open form on phone" moment. Vẫn demo được 70%.

---

### Feature 2 — Price List + Quote (Scene 2.2, 2 min)

**Có gì** (✅):
- 12 products đầy đủ theo 4 divisions (FCL 20/40, LCL, Stevedoring, Tug; Office A, Warehouse; Standard room, Suite, Conference; Customs, Freight)
- 3 pricelists: PGK Standard, USD Corporate (-5-8%), PGK VIP (-12-15%)
- `sale.order.approval.request` (threshold 10%, state machine pending/approved/rejected)
- `sale.order` inherits: `x_discount_pct`, `x_discount_amount`, `approval_state`, `x_discount_approved` (block action_confirm)
- Discount approval UI: form view + tree view + manager actions
- Currency: PGK + USD active

**Thiếu gì** (❌):

| # | Gap | DOCX ref | Effort | Priority |
|---|-----|----------|--------|----------|
| F2.1 | **Branded PDF template** (Steamships logo, PNG flag colors, payment terms) | B3 | 2h | 🟡 P1 |
| F2.2 | **Profit margin field** trên order line (INTERNAL only, ẩn trên PDF) | B3 | 1h | 🟡 P1 |
| F2.3 | **Pre-built demo quotation** với 15% discount (để show approval flow) | C2 Scene 2 | 30min | 🔴 P0 |
| F2.4 | **Contract customer pricelist** (-10%) — hiện chỉ có Standard/USD/VIP, thiếu "Contract" riêng | B3 | 15min | 🟡 P1 |
| F2.5 | **Payment terms** field trên quotation template (Net 30, etc.) | B3 | 30min | 🟡 P1 |
| F2.6 | **Email template** cho "Send by Email" (default Odoo OK nhưng cần customize) | B3 | 30min | 🟢 P2 |

**Demo impact nếu thiếu**: Discount block (15%) work, nhưng PDF trông generic. Workaround: dùng default Odoo PDF.

---

### Feature 3 — AI Chatbot RAG (Scene 2.1, 6 min — THE STAR)

**Có gì** (✅) — sau G1+G2 (2026-06-15):
- `mock_sops.py` với 15 SOPs (12 staff + 3 public visibility)
- `controllers/ai_chatbot.py` — JSON-RPC `/steamships/chat/api`, mode param (staff/client), adapter pattern (Mock | Anthropic)
- `ir.actions.client` tag=`steamships_ai_chat`
- Menu: Steamships → AI Assistant → Ask AI + Chat History
- `chat_widget.esm.js` (backend render, mode toggle, localStorage persist, mode-aware welcome)
- `__manifest__.py` đã bỏ `website` depend, JS assets → `web.assets_backend`

**Thiếu gì** (❌):

| # | Gap | DOCX ref | Effort | Priority |
|---|-----|----------|--------|----------|
| F3.1 | **FastAPI middleware** service (`/api/chat`, `/api/extract_bl`, `/api/ingest`) | B1, B4 | 4h (Day 3) | 🔴 P0 |
| F3.2 | **Ingestion pipeline** (chunk 500-1000 + overlap + embeddings) | B4 | 4h (Day 3) | 🔴 P0 |
| F3.3 | **Vector store** (pgvector Odoo 18 native, hoặc Chroma) | B1, B4 | 2h (Day 3) | 🔴 P0 |
| F3.4 | **`top_k=5`** (hiện code dùng 3) | B4 | 1min fix | 🔴 P0 |
| F3.5 | **"I don't know" fallback name team** ("Please ask Sales Operations team") | B4 | 15min | 🔴 P0 |
| F3.6 | **Source format** = `Source: SOP-XXX` (hiện trả title, cần đổi sang id) | B4 | 15min | 🔴 P0 |
| F3.7 | **SOP IDs format** `SOP-SHIP-001` thay vì `sop-001` | B4 (best practice) | 15min | 🟡 P1 |
| F3.8 | **System prompt thêm "name a person/team"** instruction | B4 | 5min | 🔴 P0 |
| F3.9 | **`ANTHROPIC_API_KEY` integration test** (khi user có key) | B4 | 30min | 🟢 P2 |
| F3.10 | **Source citation linking** (chips → Odoo `ir.attachment` / docs) | B4 | 2h | 🟢 P2 |
| F3.11 | **Test 10-20 sample SOPs** (chỉ có 15 hiện, cần thêm vài SOPs cho tour đủ) | B1 | 1h | 🟡 P1 |
| F3.12 | **Rehearse answer với exact demo question** "20ft container Lae→POM" | C2 | 30min | 🔴 P0 |

**Demo impact nếu thiếu F3.4-F3.8**: Vẫn demo được mock mode (keyword match work), nhưng:
- top-3 thay vì top-5 = ít context hơn
- Source trả title dài thay vì `Source: SOP-XXX` ngắn gọn
- "I don't know" không nêu team

**Demo impact nếu thiếu F3.1-F3.3 (FastAPI)**: Vẫn demo được (in-process mock), nhưng architecture không production-ready và cutable code nhiều hơn khi migrate real LLM.

---

### Feature 4a — Invoice OCR (Scene 4 quick, cut-able)

**Có gì**: ❌ Nothing

**Thiếu gì**:

| # | Gap | DOCX ref | Effort | Priority |
|---|-----|----------|--------|----------|
| F4a.1 | **Install Enterprise `account_invoice_extract`** module | B5a | 30min | 🟡 P1 (cut-able) |
| F4a.2 | **Configure Document Digitisation** trong Accounting settings | B5a | 15min | 🟡 P1 |
| F4a.3 | **Upload 2-3 sample supplier invoices** (PDF/photo) | B5a | 15min | 🟡 P1 |
| F4a.4 | **Test draft bill creation** + human review flow | B5a | 30min | 🟡 P1 |

**Demo impact nếu thiếu**: Bỏ qua Scene 4 quick demo (30s), vẫn có B/L reader 6 min là THE MAGIC. **Cut first per DOCX B7**.

⚠️ **Dependency**: Cần Enterprise license (Community không có module này).

---

### Feature 4b — Bill of Lading Vision (Scene 4, 6 min — THE MAGIC)

**Có gì**: ❌ Nothing

**Thiếu gì**:

| # | Gap | DOCX ref | Effort | Priority |
|---|-----|----------|--------|----------|
| F4b.1 | **`bill.of.lading` model** (13 fields + state) | B5b | 3h (Day 5) | 🔴 P0 |
| F4b.2 | **`bill.of.lading.field` model** (confidence child) | B5b | 1h (Day 5) | 🔴 P0 |
| F4b.3 | **B/L views**: tree + form (split view fields + image) | B5b | 2h (Day 6) | 🔴 P0 |
| F4b.4 | **FastAPI `/api/extract_bl` endpoint** với Claude vision | B5b | 4h (Day 6) | 🔴 P0 |
| F4b.5 | **Vision prompt** với strict JSON + confidence per field | B5b | 1h (Day 6) | 🔴 P0 |
| F4b.6 | **5 sample B/L scans** (clean/multi/skewed/**crumpled**/partial) | B5b | 2h (Day 6) | 🔴 P0 |
| F4b.7 | **Mock JSON pre-baked** cho 5 scans | B5b | 1h (Day 6) | 🔴 P0 |
| F4b.8 | **Upload + extract button** trên B/L form | B5b | 1h (Day 6) | 🔴 P0 |
| F4b.9 | **Approve action** (state → approved, chatter log) | B5b | 30min (Day 6) | 🔴 P0 |
| F4b.10 | **Low-confidence highlight** (red border + "please check" badge) | B5b | 1h (Day 6) | 🟡 P1 (cut-able) |
| F4b.11 | **ir.attachment integration** (image preview trong form) | B5b | 1h (Day 6) | 🔴 P0 |
| F4b.12 | **Menu B/L Documents** + access rights | B5b | 30min (Day 6) | 🔴 P0 |

**Demo impact nếu thiếu**: Scene 4 hoàn toàn không chạy được (B/L reader là THE MAGIC, không thể cut). **Block demo**.

⚠️ **Tổng effort F4b**: ~18h (Day 5-6).

---

### Feature 5 — Smart Booking (Scene 3, 3 min)

**Có gì**: ❌ Nothing

**Thiếu gì**:

| # | Gap | DOCX ref | Effort | Priority |
|---|-----|----------|--------|----------|
| F5.1 | **Install Enterprise `appointment` module** | B6 | 30min (Day 7) | 🔴 P0 |
| F5.2 | **2 appointment types**: Sales Call 30min, Client Onboarding 60min | B6 | 15min (Day 7) | 🔴 P0 |
| F5.3 | **Working hours GMT+10** (PNG time) | B6 | 15min (Day 7) | 🔴 P0 |
| F5.4 | **Google Calendar OAuth** cho 2 demo users | B6, B8 | 1h (Day 7 morning) | 🔴 P0 |
| F5.5 | **Test timezone conversion** (Singapore/Sydney browser) | B6 | 30min (Day 7) | 🟡 P1 |
| F5.6 | **Confirmation email** config | B6 | 15min (Day 7) | 🔴 P0 |
| F5.7 | **Auto-log meeting on CRM** (chatter post rule) | B6 | 30min (Day 7) | 🔴 P0 |

**Demo impact nếu thiếu**: Scene 3 không chạy. Demo flow mất 1 scene.

⚠️ **Tổng effort F5**: ~3h (Day 7 morning) + Google OAuth risk fiddly (DOCX B8 warning).

⚠️ **Dependency**: Cần Enterprise license.

---

## 3. Cross-cutting gaps (ảnh hưởng nhiều flows)

| # | Gap | Impact | Effort | Priority |
|---|-----|--------|--------|----------|
| X.1 | **Backup demo video** (record full 20-25 min demo) | DOCX C4, B8 | 1h | 🔴 P0 |
| X.2 | **PNG data seed** (real route names, PGK prices) | C4 | mostly done | ✅ |
| X.3 | **Rehearse ≥2 lần** với exact questions | C4 | 2h | 🔴 P0 |
| X.4 | **Phase 2 slide** (4 features cho closing) | C2 closing | 30min | 🔴 P0 |
| X.5 | **Honest-limits Q&A prep** (fake data, no security) | C4 | 30min | 🟡 P1 |
| X.6 | **Production env setup** (backup DB nightly, trial expiry 15 days) | B8 | 30min | 🟡 P1 |
| X.7 | **Internet backup** cho PNG connectivity | B8 | ongoing | 🟡 P1 |
| X.8 | **Branded assets** (logo PNG, PNG flag colors) | B3 | 1h | 🟡 P1 |

---

## 4. Đề xuất priority + plan

### Critical path (P0, block demo) — ~37h

| # | Feature | Effort | Deadline |
|---|---------|--------|----------|
| F1.1-F1.4 | Web form + auto-create lead + 24h activity | 4h | Day 1 |
| F2.3 | Pre-built 15% discount quotation | 30min | Day 2 |
| F3.1-F3.3 | FastAPI + ingestion + vector store | 10h | Day 3 |
| F3.4-F3.6, F3.8 | Mock mode fix (top_k, source format, fallback) | 1h | Day 4 |
| F4b.1-F4b.12 | B/L Vision end-to-end | 18h | Day 5-6 |
| F5.1-F5.7 | Booking + Google OAuth | 3h | Day 7 morning |
| X.1, X.3, X.4 | Backup video + rehearsal + Phase 2 slide | 3.5h | Day 7 |

### P1 (improve demo, cut-able) — ~8h

| # | Feature | Effort | Note |
|---|---------|--------|------|
| F1.5-F1.9 | 5 stages, fix industry, service_needed, stage auto | 2.5h | |
| F2.1, F2.2, F2.4, F2.5 | Branded PDF, margin, Contract pricelist, payment terms | 3.5h | |
| F3.7, F3.11 | SOP IDs format, thêm 5 SOPs | 1.5h | |
| F4b.10 | Low-confidence highlight | 1h | Cut per B7 |
| F4a.1-F4a.4 | Invoice OCR config | 1.5h | Cut per B7 |
| F5.5 | Timezone test | 30min | |
| X.5, X.6, X.8 | Demo prep | 2h | |

### P2 (polish, post-demo) — ~3h

| # | Feature | Effort | Note |
|---|---------|--------|------|
| F1.10 | Thêm Madang, Rabaul branches | 15min | |
| F2.6 | Email template customize | 30min | |
| F3.9, F3.10 | Real LLM test + source linking | 2.5h | |

---

## 5. Realistic assessment

**Đã có**: foundation ~40% (data, models, basic flows, mock AI)

**Còn thiếu**: ~60%, tập trung vào:
- **AI infrastructure** (FastAPI + ingestion + vector store) — 10h
- **B/L Vision end-to-end** (THE MAGIC, 6 min scene) — 18h
- **Booking + OAuth** (Enterprise-dependent) — 3h
- **Demo polish** (PDF, web form, branded assets) — 8h

**Timeline assessment** vs DOCX 7-day plan:
- Day 1-2 (config + data): ✅ on track (thiếu web form + branded PDF = 6h)
- Day 3-4 (RAG): 🟡 **risk** — FastAPI chưa có, cần 10h
- Day 5-6 (B/L): 🔴 **high risk** — 18h, lớn nhất
- Day 7 (Booking + rehearsal): 🟡 **risk** — Google OAuth fiddly

**Cut nếu trễ** (theo DOCX B7):
1. Client-mode chatbot toggle (đã có, dễ drop)
2. Invoice OCR part
3. Simplify B/L review screen (bỏ low-conf highlight)
4. **KHÔNG cut**: Feature 1, 2, staff chatbot, B/L reader

---

## 6. Immediate next steps (session này)

Sau G1+G2 (chat backend + modes), recommend làm theo thứ tự:

1. **Mock mode fixes** (F3.4-F3.6, F3.8) — 1h, quick win, làm ngay
2. **FastAPI skeleton** (F3.1) — 4h, foundation cho Day 3
3. **Web onboarding form** (F1.1-F1.4) — 4h, Day 1 critical
4. **B/L model** (F4b.1-F4b.2) — 4h, foundation cho Day 5
5. **Pre-built demo quotation** (F2.3) — 30min, Day 2 quick win
6. **PNG data cleanup** (F1.10, F3.7) — 30min, polish

Tổng immediate: ~14h, có thể nhồi Day 1-2-3.

Bạn muốn tôi làm item nào tiếp theo?
