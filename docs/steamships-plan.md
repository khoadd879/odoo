# Steamships Odoo Prototype — Implementation Plan

> Source: `Steamships Odoo Prototype Plan.docx` (June 2026, Confidential)
> Target: 1-week build (1 dev), 5 features, demo day = Day 7

---

## 0. Tổng quan yêu cầu từ DOCX

**Client**: Steamships Trading Company (PNG, 3000 staff, listed on ASX + POMSoX)
**4 divisions**:
1. Shipping & Logistics — Consort fleet 20 ships, 17 ports, 8000+ containers, Pacific Towing tug boats
2. Property — offices, shops, warehouses, homes for lease
3. Hotels & Hospitality
4. JVs — 20+ part-owned (Colgate Palmolive PNG 50%)

**5 problems → 5 features**:
| # | Problem | Feature |
|---|---------|---------|
| 1 | New staff make basic mistakes (8/10 hires) | AI helpers, RAG chatbot |
| 2 | No CRM (lost docs, 3 onboarding forms) | 1 CRM + 1 onboarding form |
| 3 | Merged companies don't fit | Unified onboarding + price list |
| 4 | Nobody knows what to quote | Trusted price list + quote maker |
| 5 | Time-zone scheduling hell | Smart booking + Google Cal |
| 6 | Document-heavy (B/L, invoices) | AI document reader |

**Rule**: Build demo path first, polish later. Each feature only needs to work for demo script (Part C of DOCX).

---

## 1. Phân tích hiện trạng → Cần xóa gì

### 1.1 Modules hiện tại (custom/) — KHÔNG LIÊN QUAN

| Module | Tình trạng | Action |
|---|---|---|
| `vn_phone_shop` | VN localization cho phone retail (iPhone, Samsung) | **XÓA TOÀN BỘ** |
| `phone_shop_demo` | Phone products/customers/warehouses demo data | **XÓA TOÀN BỘ** |
| `phone_importer` | Empty JSON helper (no code) | **XÓA TOÀN BỘ** |
| `hello_shop` (status=deleted in git) | Demo scaffold | Đã xóa, skip |
| `mail_gmail_setup` (status=deleted in git) | Gmail SMTP provisioning | Đã xóa, skip |
| `product_note` (status=deleted in git) | Product note feature | Đã xóa, skip |

### 1.2 DB hiện tại — KHÔNG LIÊN QUAN

DB `odoo_dev` chứa:
- Company "My Company" (US-based) + "VN Company" (vi-VN)
- Phone brands (Apple/Samsung/Xiaomi/OPPO/Vivo/Realme/Nokia)
- Phone products (iPhone 15 PM, Samsung S24 Ultra...)
- 21 phone products + accessories
- 24 customers (Nguyễn Văn An, Trần Thị Bình, Cty CP Mobile Hà Nội...)
- 5 suppliers (Apple VN, Samsung VN, etc.)
- 7 warehouses (Kho Tổng, Kho Phụ, Cửa Hàng, etc.)
- POS config (Phone Shop - Cửa Hàng Chính)
- 7 CRM teams (Online Sales, Marketplace, B2B Direct, Customer Support)
- 14 payment terms (VN localized)

**Tất cả phải XÓA** vì:
- Currency: VND (DOCX yêu cầu PGK + USD)
- Country: VN (DOCX yêu cầu PG = Papua New Guinea)
- Domain: phone retail (DOCX yêu cầu shipping/property/hotels)
- Brand names: phone brands (DOCX yêu cầu Steamships Trading)

### 1.3 Kế hoạch reset sạch

**Drop DB**:
```bash
docker compose stop odoo
docker compose exec db psql -U odoo -d postgres -c "DROP DATABASE odoo_dev"
docker run --rm -v $(pwd)/odoo-data:/data alpine sh -c "rm -rf /data/filestore/odoo_dev /data/sessions"
```

**Xóa 3 modules**:
```bash
rm -rf addons/custom/vn_phone_shop
rm -rf addons/custom/phone_shop_demo
rm -rf addons/custom/phone_importer
```

**Add new module**: `addons/custom/steamships_demo/`

---

## 2. Modules cần install từ Odoo (theo DOCX B1)

| Module | Mục đích | Status |
|---|---|---|
| `crm` | Feature 1 - CRM pipeline | Core, free |
| `sale` | Feature 1, 2 - Quotation | Core, free |
| `website` | Feature 1 - Onboarding form | Core, free |
| `website_form` | Feature 1 - Web form builder | Auto with website |
| `documents` | Feature 1 - Document attachment | Enterprise ONLY (free trial) |
| `account` | Feature 2, 4 - Accounting | Core, free |
| `account_invoice_extract` (alias `iap_alternative_service`) | Feature 4a - Invoice OCR | **Enterprise ONLY** |
| `appointment` (alias `website_appointment`) | Feature 5 - Smart booking | Enterprise ONLY |
| `google_calendar` | Feature 5 - Calendar sync | Core, free |
| `l10n_pg` | Locale - Papua New Guinea | Check exists |
| `utm` | CRM tracking | Core, free |
| `mail` | Email tracking | Core, free |

**Risk**: DOCX nói dùng **Odoo 18 Enterprise trial**. Current setup là Community (Docker build từ `odoo:18.0`). Một số features (invoice OCR, documents app, appointments) chỉ có trong Enterprise.

**Mitigation (Day 1)**:
- Nếu user có Enterprise license → install Enterprise trial
- Nếu không → dùng Community workarounds:
  - **Documents app** → thay bằng `ir.attachment` + custom menu
  - **Invoice OCR** → tạm bỏ qua (DOCX nói "cut in this order — first drop the client-mode chatbot toggle, then drop the invoice OCR part")
  - **Appointments** → thay bằng website form + custom meeting model

---

## 3. Module mới: `addons/custom/steamships_demo/`

### 3.1 Structure

```
addons/custom/steamships_demo/
├── __init__.py
├── __manifest__.py
├── security/
│   └── ir.model.access.csv
├── models/
│   ├── __init__.py
│   ├── bill_of_lading.py          # Feature 4b - custom model
│   ├── shipment.py                # Container shipping records
│   ├── property_lease.py          # Property division
│   ├── hotel_booking.py           # Hospitality division
│   ├── jv_partner.py              # JV tracking
│   ├── chatbot_session.py         # Feature 3 - RAG chat log
│   ├── appointment_slot.py        # Feature 5 - time-zone aware
│   └── onboarding_checklist.py    # Feature 1 - doc checklist
├── data/
│   ├── company_steamships.xml     # 1 main company + 4 divisions
│   ├── currency_pgk.xml           # PGK currency
│   ├── l10n_pg_chart.xml          # Chart of accounts (basic)
│   ├── products_logistics.xml     # Container FCL 20/40, LCL, Stevedoring
│   ├── products_property.xml      # Office lease, warehouse, shop
│   ├── products_hotel.xml         # Room nights, F&B, events
│   ├── pricelists.xml             # Standard, Contract, JV
│   ├── customers_corporate.xml    # 10 sample B2B clients
│   ├── customers_jv.xml           # 5 JV partners (Colgate PNG etc.)
│   ├── sale_team_steamships.xml   # 4 sales teams (1 per division)
│   ├── crm_stages.xml             # 5 stages pipeline
│   ├── sop_documents.xml          # 15 SOPs for RAG
│   ├── sample_bl_scans.xml        # 5 B/L demo scans
│   ├── sample_invoices.xml        # 3 supplier invoice scans
│   ├── onboarding_form.xml        # Web form definition
│   └── appointment_types.xml      # Sales Call 30min, Onboarding 60min
├── views/
│   ├── bill_of_lading_views.xml
│   ├── shipment_views.xml
│   ├── property_lease_views.xml
│   ├── hotel_booking_views.xml
│   ├── jv_partner_views.xml
│   ├── chatbot_session_views.xml
│   ├── appointment_slot_views.xml
│   ├── onboarding_checklist_views.xml
│   ├── crm_inherited_views.xml
│   ├── product_inherited_views.xml
│   ├── menu_desktop.xml
│   └── menu_website.xml
├── security/
│   ├── ir.model.access.csv
│   └── security_groups.xml
├── middleware/
│   ├── fastapi_app/
│   │   ├── main.py                # FastAPI entry
│   │   ├── routes/
│   │   │   ├── chat.py            # RAG endpoint
│   │   │   ├── extract_bl.py      # Vision endpoint
│   │   │   └── ingest.py          # Document ingestion
│   │   ├── services/
│   │   │   ├── embeddings.py      # pgvector or chroma
│   │   │   ├── llm_client.py      # Mockable (api key or mock)
│   │   │   ├── vector_store.py
│   │   │   └── prompt_templates.py
│   │   ├── data/
│   │   │   └── sample_sops/       # 15 SOPs (text files)
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── docker-compose.override.yml
├── static/
│   └── description/
│       └── index.html             # Module description
└── demo/
    ├── demo_crm_leads.xml
    ├── demo_quotations.xml
    ├── demo_shipments.xml
    ├── demo_appointments.xml
    └── demo_chatbot_sessions.xml
```

### 3.2 `__manifest__.py` (draft)

```python
{
    'name': 'Steamships Trading - PNG Demo',
    'version': '18.0.1.0.0',
    'category': 'Demo/PNG',
    'summary': 'Steamships Trading 1-week prototype: CRM, RAG, B/L reader, booking',
    'depends': [
        'base', 'mail', 'utm',
        'crm', 'sale', 'sale_management',
        'website', 'website_form',
        'account', 'account_payment',
        'stock', 'purchase',
        'google_calendar',
        # Enterprise (optional)
        # 'documents', 'appointment', 'account_invoice_extract',
    ],
    'data': [
        # Core config
        'data/company_steamships.xml',
        'data/currency_pgk.xml',
        'data/l10n_pg_chart.xml',
        # Products
        'data/products_logistics.xml',
        'data/products_property.xml',
        'data/products_hotel.xml',
        'data/pricelists.xml',
        # CRM
        'data/sale_team_steamships.xml',
        'data/crm_stages.xml',
        'data/customers_corporate.xml',
        'data/customers_jv.xml',
        # Onboarding
        'data/onboarding_form.xml',
        'data/onboarding_checklist.xml',
        # SOPs for RAG
        'data/sop_documents.xml',
        # Booking
        'data/appointment_types.xml',
        # AI models
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        # Views
        'views/menu_desktop.xml',
        'views/menu_website.xml',
        'views/crm_inherited_views.xml',
        'views/product_inherited_views.xml',
        'views/shipment_views.xml',
        'views/property_lease_views.xml',
        'views/hotel_booking_views.xml',
        'views/jv_partner_views.xml',
        'views/bill_of_lading_views.xml',
        'views/chatbot_session_views.xml',
        'views/appointment_slot_views.xml',
        'views/onboarding_checklist_views.xml',
    ],
    'demo': [
        'demo/demo_crm_leads.xml',
        'demo/demo_quotations.xml',
        'demo/demo_shipments.xml',
        'demo/demo_appointments.xml',
        'demo/demo_chatbot_sessions.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
    'author': 'khoa',
}
```

---

## 4. Implementation plan theo 7-day timeline (DOCX B7)

### Day 1: Reset + Setup + Feature 1 (CRM + Onboarding)

**Tasks**:
1. [x] Stop Odoo, drop DB `odoo_dev`
2. [x] Xóa 3 modules phone
3. [ ] Create `addons/custom/steamships_demo/` skeleton
4. [ ] `__manifest__.py` với depends
5. [ ] Init DB với `base, l10n_pg, crm, sale, website, account, google_calendar, steamships_demo --without-demo=all`
6. [ ] **Feature 1a - CRM pipeline**: 5 stages
   - Lead → Qualified → Onboarding Docs → Quoted → Won/Lost
   - File: `data/crm_stages.xml`
7. [ ] **Feature 1b - Single onboarding form**:
   - Website form với fields: company, contact, email, phone, country, industry (dropdown: Logistics/Property/Hospitality/JV), service needed, multi-file upload
   - All required fields
   - On submit: auto-create CRM lead, attach files, auto-assign salesperson, create 24h activity reminder
   - File: `data/onboarding_form.xml`
8. [ ] **Feature 1c - Document checklist** (custom field on res.partner):
   - registration_form (bool), kyc_docs (bool), signed_terms (bool)
   - File: `models/onboarding_checklist.py`

**Done when** (from DOCX):
- Submitting form → lead with files attached in <5s
- Full chatter log visible

### Day 2: Feature 2 (Price list + Quote)

**Tasks**:
1. [ ] **Products catalog** (3 divisions):
   - `data/products_logistics.xml`: Container FCL 20ft Lae→POM, FCL 40ft, LCL per m³, Stevedoring per move, Tug assist
   - `data/products_property.xml`: Office lease per m²/month, Warehouse per m²/day, Shop lease
   - `data/products_hotel.xml`: Standard room/night, Suite/night, F&B package, Event venue
2. [ ] **Price lists** (`data/pricelists.xml`):
   - Standard (PGK)
   - Contract customer (10% lower)
   - JV partner (15% lower, requires approval)
   - USD pricelist for international clients
3. [ ] **Currency setup**:
   - PGK (Papua New Guinea Kina) — ID, rate vs USD
   - USD (already exists)
   - File: `data/currency_pgk.xml`
4. [ ] **Branded quotation template**:
   - Logo placeholder, Steamships colors (PNG flag colors: red+black+yellow)
   - Payment terms section
   - Internal margin column (not in PDF)
5. [ ] **Discount approval** (Odoo config):
   - Sale settings → Discount: require manager approval > 10%
6. [ ] **Demo data**: 3 quotations with 1 at 15% discount (to show approval flow)

**Done when** (from DOCX):
- Pick client + 3 services + branded PDF + email <2min
- 15% discount blocked + manager approval popup

### Day 3: Feature 3a (RAG pipeline — the brain)

**Tasks**:
1. [ ] Create `middleware/fastapi_app/` service
2. [ ] **Document ingestion**:
   - 15 sample SOPs (text files in `middleware/data/sample_sops/`)
   - Examples: SOP-SHIP-004 (container booking docs), SOP-LEASE-002 (lease terms), SOP-HOTEL-001 (group booking), etc.
   - Chunk 500-1000 chars, create embeddings (mock if no API key)
3. [ ] **Vector store**:
   - Try pgvector first (Odoo 18 has built-in support)
   - Fallback Chroma (separate service)
4. [ ] **Answer endpoint** (`/api/chat`):
   - Take question → top 5 chunks → LLM (or mock) → answer + source citations
5. [ ] **System prompt** (DOCX exact):
   ```
   Answer ONLY from the provided documents. If the answer is not in the documents,
   say you do not know and name a person/team to ask. Always cite your sources.
   ```
6. [ ] **Modes toggle** (staff vs client):
   - Staff: search SOPs + price list + internal policies
   - Client: search onboarding help + FAQ (no prices, no SOPs)
7. [ ] **Mock LLM** (no API key):
   - `llm_client.py` with adapter pattern
   - `MockLLMClient` returns canned response with first 2 chunks quoted

**Done when**:
- Q: "20ft container Lae→POM, what price + what docs?" → returns price + SOP-SHIP-004 citation
- Q: something not in docs → "I don't know, please ask X team"

### Day 4: Feature 3b (Chat UI)

**Tasks**:
1. [ ] Build chat UI:
   - Option A: standalone HTML/JS page (`middleware/fastapi_app/static/chat.html`)
   - Option B: embedded iframe in Odoo website
   - Use Steamships colors (red/black/yellow from PNG flag)
2. [ ] Wire to FastAPI endpoint
3. [ ] Mode toggle (Staff/Client)
4. [ ] Display source citations as clickable links to Odoo documents
5. [ ] **Log all sessions** to `chatbot.session` Odoo model (via JSON-RPC)

**Done when**:
- Open chat in browser → ask demo question → answer + sources appear
- Toggle modes → different doc sets returned

### Day 5: Feature 4a (Invoice OCR config) + 4b start (B/L model)

**Tasks**:
1. [ ] **4a - Invoice OCR** (Enterprise only, otherwise skip per DOCX advice):
   - Accounting → Settings → Document Digitisation ON
   - Upload 3 sample supplier invoices (PDF/photo)
   - Verify draft bills created with vendor/date/amounts
2. [ ] **4b - Bill of Lading custom model** (`models/bill_of_lading.py`):
   - Fields: bl_number, shipper, consignee, notify_party, vessel_name, voyage_number, container_numbers (One2many or text), port_loading, port_discharge, cargo_description, weight, date, status (Draft/Pending Review/Approved), file_attachment
   - `status` workflow: Draft → Pending Review (after AI) → Approved (human click)
2b. [ ] **Confidence score** per field (Dict or One2many to `bl_field` child):
   - `bl.field` model: bl_id, field_name, value, confidence (high/med/low)
   - Low-confidence fields highlight in review form

**Done when**:
- Can manually create B/L record via UI
- Status workflow works

### Day 6: Feature 4b finish (Vision extraction)

**Tasks**:
1. [ ] **Extraction endpoint** (`/api/extract_bl`):
   - Upload image/PDF → send to vision API (or mock) with prompt: "Return strict JSON: {bl_number, shipper, consignee, ...} with confidence per field"
   - MockVisionClient: returns pre-baked JSON for 5 sample scans
2. [ ] **Write to Odoo**:
   - Create B/L record via Odoo JSON-RPC (`/web/dataset/call_kw`)
   - Status = Pending Review
3. [ ] **Review screen**:
   - Form view: extracted fields (left) + original image (right)
   - Low-confidence fields: warning tag, "please check"
   - Reviewer fixes + clicks Approve
4. [ ] **5 sample B/L scans**:
   - Stored in `middleware/data/sample_bls/`
   - 1 crumpled/skewed for "wow factor" (DOCX requirement)
   - Each paired with mock JSON for the 5 sample files

**Done when**:
- Upload B/L photo → filled record in <30s
- Human approves in 1 click
- Demo: 12min typing → 20s AI + check

### Day 7: Feature 5 (Booking) + Rehearsal

**Tasks**:
1. [ ] Install `appointment` (Enterprise) or build custom with `website_calendar`:
   - 2 appointment types: Sales Call 30min, Client Onboarding 60min
   - Working hours: GMT+10 (PNG time)
   - Booking page auto-detects visitor time zone
2. [ ] **Google Calendar OAuth setup** for 2 demo users:
   - Use Odoo's native Google Calendar connector
   - Do this EARLY morning (DOCX risk warning)
3. [ ] **CRM integration**:
   - Each booking → log as meeting on client's CRM record
   - Confirmation email on
4. [ ] **Seed PNG sample data** (DOCX C4):
   - Real route names: Lae, Port Moresby, Madang, Rabaul
   - PGK prices (K100, K1000 etc.)
   - PNG-flag-themed branding
5. [ ] **Rehearse full demo** (≥2 times):
   - Scene 1: Onboarding 4min
   - Scene 2: AI bot + quote 6min (THE STAR)
   - Scene 3: Booking 3min
   - Scene 4: B/L reader 6min (THE MAGIC)
   - Closing: Phase 2 slide 3min
6. [ ] **Record backup video** of full demo
7. [ ] **Prepare Phase 2 slide**:
   - AI note-taker
   - AI proposal/pitch-deck
   - AI migration of old data
   - Group-wide JV consolidation

**Done when**:
- All 4 scenes runnable in 20-25min
- Backup video recorded
- Phase 2 slide ready

---

## 5. AI Features - Mock Implementation Plan (no API key)

Per user choice "bạn vẫn thêm feature AI nhưng khoan có api key":

### 5.1 LLM Client abstraction (`llm_client.py`)

```python
class BaseLLMClient:
    def complete(self, system: str, user: str) -> str: ...
    def embed(self, text: str) -> list[float]: ...
    def extract_bl(self, image_path: str, prompt: str) -> dict: ...

class MockLLMClient(BaseLLMClient):
    """Returns canned responses. Used when no API key set."""
    def complete(self, system, user):
        # Grep mock_sops/ for keyword, return first 2 chunks as if answer
        ...
    def extract_bl(self, image_path, prompt):
        # Load pre-baked JSON from middleware/data/sample_bls/{filename}.json
        ...

class AnthropicLLMClient(BaseLLMClient):
    """Real Anthropic API. Activated when ANTHROPIC_API_KEY env var set."""
    ...

def get_llm_client() -> BaseLLMClient:
    if os.getenv('ANTHROPIC_API_KEY'):
        return AnthropicLLMClient()
    return MockLLMClient()  # default
```

### 5.2 Mock behavior
- **Chat**: Grep SOP files for keyword match, return first 2 chunks formatted as answer
- **Embeddings**: Use simple TF-IDF or hash-based vector (no real semantic search, but works for demo)
- **B/L extraction**: Pre-baked JSON per sample scan
- **Honest**: UI shows "(MOCK MODE — set ANTHROPIC_API_KEY for real AI)" badge

### 5.3 Future migration to real API
- Just set `ANTHROPIC_API_KEY` env var → `get_llm_client()` returns real client
- No code changes needed
- pgvector embeddings can stay (Chroma fallback too)

---

## 6. Risks & Honest Warnings (from DOCX B8)

| Risk | Mitigation |
|---|---|
| Enterprise trial expires 15 days | Start trial Day 1. Backup DB nightly. |
| AI wrong answer live in demo | Rehearse with exact demo questions. Prompt forces "I don't know". |
| Google OAuth fiddly | Day 7 morning, not 1 hour before. Test both demo users. |
| Vision misreads bad scan | Pre-test 5 samples. Use worst ONLY if works reliably. |
| Confidential data questions | Prepare answer: "fake data, production covers residency/security in Phase 2". |
| Internet drops (PNG connectivity) | Recorded backup video. Always. |

---

## 7. Cut Order (if running behind, DOCX B7)

Drop in this order:
1. **Client-mode chatbot toggle** (keep staff mode, it's the star)
2. **Invoice OCR part** (keep B/L reader, it's flashier)
3. **Simplify review screen** (just show fields + Approve button, skip low-confidence highlighting)

**NEVER cut**: Features 1, 2, or staff chatbot (they carry the demo story).

---

## 8. Out of scope (Phase 2)

- Real company data migration
- PNG tax setup (GST, withholding)
- Production security + access rights per division
- Group-wide accounting consolidation across JVs
- AI note-taker for meetings
- AI proposal/pitch-deck generator

---

## 9. Next steps for THIS session (per user choice)

User picked:
- ✅ Xóa 3 modules phone, build lại
- ✅ Setup + Feature 1 + Feature 2
- ✅ Add AI feature structure (mock mode, no API key)

**Will do in this session** (one turn, with sub-agents for parallel work):

### Phase A: Cleanup (sequential)
1. Stop Odoo, drop DB
2. Xóa `addons/custom/vn_phone_shop/`, `phone_shop_demo/`, `phone_importer/`
3. Verify

### Phase B: Module skeleton (sequential)
4. Create `addons/custom/steamships_demo/` structure
5. Write `__manifest__.py`
6. Write `models/__init__.py` skeleton

### Phase C: Setup + Day 1-2 (parallel via 2-3 sub-agents)
7. **Agent 1**: Company + currency + chart of accounts XML
8. **Agent 2**: Products XML (3 divisions, ~20 services) + pricelists
9. **Agent 3**: CRM pipeline + onboarding form XML + customers

### Phase D: Init + verify
10. Init DB: `base, l10n_pg (or generic), crm, sale, website, account, google_calendar, steamships_demo --without-demo=all`
11. Verify all 5 features structure loadable

### Phase E: AI structure (deferred to next turn, or partial)
12. Create `middleware/fastapi_app/` skeleton (no LLM call)
13. Mock LLM client
14. 15 sample SOPs (text files)
15. Chat UI (HTML/JS, standalone)

### Phase F: Report
16. Summary to user
17. Known gaps
18. Ask for confirmation to continue with Day 3-7 features
