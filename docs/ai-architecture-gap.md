# Steamships AI — Architecture & Gap Report

> Source: `steamships-plan.docx` Part A (A2, A4), Part B (B4, B5), Part C (C2)
> Scope: 3 AI features (RAG Chatbot, Invoice OCR, B/L Vision)
> Status: 2026-06-15, post-module-audit

---

## 1. 3 AI Features theo DOCX

DOCX chỉ rõ **3 features AI**, tất cả **hỗ trợ staff nội bộ** (giải quyết Problem 1 — "8/10 new hires make basic errors"):

| # | Feature | Ai dùng? | Use case (nguyên văn DOCX) | Demo scene |
|---|---------|----------|----------------------------|------------|
| 3 | **RAG Chatbot** | Staff nội bộ (chính) + Client (phụ) | "staff ask questions in normal language and get correct answers based on the COMPANY'S OWN documents, with the source shown" | Scene 2 (THE STAR) |
| 4a | **Invoice OCR** | Staff kế toán | "supplier invoices... Odoo creates DRAFT bills with vendor, date, amounts pre-filled. A human reviews and posts" | Scene 4 (quick demo) |
| 4b | **Bill of Lading Vision** | Staff shipping | "AI does the typing; your people do the judging" | Scene 4 (THE MAGIC) |

**Cut order** (DOCX B7): nếu trễ deadline → drop theo thứ tự: client-mode chatbot toggle → invoice OCR → simplify review screen. **Không bao giờ** drop staff chatbot, Feature 1, Feature 2.

---

## 2. Kiến trúc

DOCX B1 chỉ rõ: **Odoo = UI/data layer**, **AI = dịch vụ ngoài** (FastAPI middleware → Claude API).

```
┌──────────────────────────────────────────────────────────┐
│  Odoo 18 (Community docker / Enterprise trial)          │
│  ───────────────────────────────────────────────         │
│  Staff dùng BACKEND Odoo (admin UI, không phải website) │
│  ─ Menu Steamships → Ask AI        (RAG chat)           │
│  ─ Menu Steamships → B/L Documents (review + approve)   │
│  ─ ir.attachment cho uploaded scans                      │
│  ─ chatter log cho mọi AI action (audit)                │
└─────────────────┬────────────────────────────────────────┘
                  │ JSON-RPC / XML-RPC
┌─────────────────▼────────────────────────────────────────┐
│  FastAPI Middleware (Docker service, port 8000)         │
│  ──────────────────────────────────────────────         │
│  POST /api/chat          (RAG: query → top-5 chunks)    │
│  POST /api/extract_bl    (Vision: img → JSON+confidence)│
│  POST /api/ingest        (chunks + embeddings)          │
│  GET  /api/healthz                                    │
│  ─ Vector store: pgvector (Odoo 18 native) hoặc Chroma  │
│  ─ LLM client: adapter pattern (Anthropic | Mock)       │
│  ─ System prompt: "Answer ONLY from documents..."        │
└─────────────────┬────────────────────────────────────────┘
                  │ HTTPS (ANTHROPIC_API_KEY env var)
┌─────────────────▼────────────────────────────────────────┐
│  Anthropic Claude API                                    │
│  ─ claude-haiku-4-5-20251001 (text) cho RAG             │
│  ─ claude-sonnet-4-6 (vision) cho B/L extraction        │
│  ─ Budget: USD 20-50 cho cả 1-week demo (DOCX B1)       │
└──────────────────────────────────────────────────────────┘
```

**Mock mode** (khi không có `ANTHROPIC_API_KEY`):
- `MockLLMClient` thay `AnthropicLLMClient` qua `get_llm_client()` factory
- RAG: keyword match `mock_sops.py` (15 SOPs)
- B/L: pre-baked JSON cho 5 sample scans
- UI hiện badge "(MOCK MODE — set ANTHROPIC_API_KEY for real AI)"

---

## 3. RAG Chatbot (Feature 3) — chi tiết

### 3.1 Use case chính (DOCX B4, C2 Scene 2)

Nhân viên mới hỏi chatbot trong Odoo backend → nhận answer đúng + source name từ tài liệu công ty.

**Demo question (nguyên văn)**:
> *"A client wants to ship a 20ft container from Lae to Port Moresby — what do I quote and what documents do I need?"*

**Bot phải trả**: price (PGK 4,500) + document list + source "SOP-SHIP-004".

**Demo honesty question** (ngoài knowledge base) → bot nói: *"I don't know, please ask X team."*

### 3.2 System prompt (nguyên văn DOCX)

```
Answer ONLY from the provided documents. If the answer is not in the documents,
say you do not know and name a person/team to ask. Always cite your sources.
```

### 3.3 Ingestion pipeline (Day 3)

| Bước | Input | Output |
|------|-------|--------|
| Collect | 10-20 sample docs (text/md/pdf) | Raw files |
| Chunk | raw text | 500-1000 char chunks, overlap 100 |
| Embed | chunks | float[1536] vectors (Anthropic `voyage-3` hoặc mock hash) |
| Store | vectors + metadata {doc_name, section, page} | pgvector table / Chroma collection |

**Mock ingest** (no API key): chunk + keyword index (BM25-lite) trong in-memory dict.

### 3.4 2 modes (toggle)

| Mode | Allowed docs | Use case | Cắt được? |
|------|--------------|----------|-----------|
| **STAFF** (default, star) | SOPs + price list + policies | Nhân viên nội bộ tra cứu | ❌ NEVER cut |
| **CLIENT** | Onboarding help + FAQ (NO prices, NO SOPs) | Public-facing optional | ✅ Cut first per DOCX B7 |

Toggle chỉ **switch document set** trong retrieval (filter `metadata['visibility']`), không phải 2 LLM riêng.

### 3.5 Source citation

Mỗi chunk có metadata `{doc_id, doc_name, section, page, url}`. Response format:
```json
{
  "answer": "FCL 20ft Lae→POM: PGK 4,500. Required docs: ...",
  "sources": [
    {"name": "SOP-SHIP-004", "section": "Container booking docs", "score": 0.89},
    {"name": "Price List 2026", "section": "Logistics", "score": 0.76}
  ]
}
```

UI render sources as clickable chips → link tới Odoo `ir.attachment` / `documents.document` của file gốc.

---

## 4. Invoice OCR (Feature 4a) — chi tiết

### 4.1 Use case

Kế toán upload PDF/photo supplier invoice → Odoo tạo DRAFT bill với vendor/date/amounts pre-filled → human reviews + posts.

### 4.2 Approach (DOCX B5 a)

**CONFIG ONLY**, không code:
1. Install Enterprise module `account_invoice_extract` (alias `iap_alternative_service`)
2. Accounting → Settings → Document Digitisation → ON
3. Upload 2-3 sample supplier invoices (PDF/photo)
4. Odoo tạo DRAFT vendor bill tự động
5. Human clicks "Post" sau khi review

**Cut order**: drop đầu tiên nếu trễ (DOCX B7). Lý do: Enterprise-only, cần IAP credits, B/L reader flashier hơn.

### 4.3 Community fallback (nếu không có Enterprise)

Thay bằng `ir.attachment` + manual review checklist. Mất demo "wow" nhưng giữ flow "AI does typing, human approves".

---

## 5. Bill of Lading Vision (Feature 4b) — chi tiết

### 5.1 Use case

Nhân viên shipping upload ảnh B/L (có thể crumpled/skewed) → AI Vision extract 13 fields + confidence per field → status `Pending Review` → human check low-conf fields → click `Approve`.

**Demo comparison** (DOCX C2 Scene 4):
- Manual: ~12 min typing, nhiều lỗi
- AI: ~20s AI + human check 1 click

### 5.2 Custom Odoo model

```python
# models/bill_of_lading.py
class BillOfLading(models.Model):
    _name = 'bill.of.lading'
    _inherit = ['mail.thread']
    _description = 'Bill of Lading (Shipping Document)'

    name = fields.Char(compute='_compute_name', store=True)  # = bl_number
    bl_number = fields.Char(string='B/L Number', required=True, index=True)
    shipper = fields.Char()
    consignee = fields.Char()
    notify_party = fields.Char()
    vessel_name = fields.Char()
    voyage_number = fields.Char()
    container_numbers = fields.Text()  # newline-separated
    port_loading = fields.Char()
    port_discharge = fields.Char()
    cargo_description = fields.Text()
    weight_kg = fields.Float()
    bl_date = fields.Date()

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
    ], default='draft', tracking=True)

    attachment_id = fields.Many2one('ir.attachment', string='Original scan')
    field_ids = fields.One2many('bill.of.lading.field', 'bl_id', string='Field confidence')

# models/bill_of_lading_field.py
class BillOfLadingField(models.Model):
    _name = 'bill.of.lading.field'

    bl_id = fields.Many2one('bill.of.lading', ondelete='cascade')
    field_name = fields.Char(required=True)
    field_value = fields.Char()
    confidence = fields.Selection([
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ])
    reviewed = fields.Boolean(default=False)
```

### 5.3 Vision extraction endpoint (FastAPI)

**Request**:
```json
POST /api/extract_bl
{
  "bl_id": 42,
  "image_b64": "...",
  "filename": "scan_crumpled.jpg"
}
```

**Vision prompt** (gửi Claude Sonnet):
```
You are extracting structured data from a Bill of Lading scan.
Return STRICT JSON only, no commentary:
{
  "bl_number": "...",
  "shipper": "...",
  "consignee": "...",
  "notify_party": "...",
  "vessel_name": "...",
  "voyage_number": "...",
  "container_numbers": ["...", "..."],
  "port_loading": "...",
  "port_discharge": "...",
  "cargo_description": "...",
  "weight_kg": 0.0,
  "bl_date": "YYYY-MM-DD",
  "confidence": {
    "bl_number": "high|medium|low",
    "shipper": "high|medium|low",
    ... // one per field
  }
}
If a field is illegible, set value to null and confidence to "low".
```

**Response** (Odoo ghi vào DB):
```json
{
  "ok": true,
  "bl_id": 42,
  "fields": {"bl_number": "PNG-2026-0042", ...},
  "confidence": {"bl_number": "high", "shipper": "medium", ...}
}
```

**Mock vision** (no API key): load pre-baked JSON từ `middleware/data/sample_bls/{filename}.json`.

### 5.4 Review form view (Odoo backend)

**Layout**: 2 cột side-by-side
- **Left**: extracted fields (form) — low-confidence fields có badge đỏ "⚠ please check" + border highlight
- **Right**: original scan (image preview từ `ir.attachment`)

**Header buttons**:
- `[Re-extract]` (gọi lại vision, nếu scan mới hơn)
- `[Approve]` (state → approved, ghi chatter log)
- `[Edit fields]` (sửa trước khi approve)

### 5.5 Sample scans

5 file trong `middleware/data/sample_bls/`:
1. `bl_clean_001.jpg` — clean scan, mọi field high confidence
2. `bl_clean_002.png` — clean, multi-container
3. `bl_skewed_003.jpg` — scan nghiêng 15°
4. `bl_crumpled_004.jpg` — **crumpled/skewed, THE WOW** (DOCX C2)
5. `bl_partial_005.jpg` — bottom cut off, 1-2 fields low confidence

Mỗi file có `.json` pre-baked (mock mode) + actual image (real vision test).

---

## 6. Hiện trạng code (đã audit 2026-06-15)

### 6.1 Có gì (existing)

| File | Status | Note |
|------|--------|------|
| `mock_sops.py` (15 SOPs) | ✅ | Keyword search; works for mock RAG |
| `controllers/ai_chatbot.py` (route + adapter) | ⚠️ | Logic đúng nhưng UI sai (website=True) |
| `models/crm_lead_link.py` (link lead↔onboarding) | ✅ | Feature 1 |
| `models/crm_lead_onboarding.py` (KYC checklist) | ✅ | Feature 1 |
| `models/sale_order_approval.py` (discount > 10%) | ✅ | Feature 2 |
| `models/division.py`, `branch.py` | ✅ | Master data |
| `data/product_data.xml`, `pricelist_data.xml` | ✅ | Feature 2 |
| `data/currency_data.xml` (PGK) | ✅ | |

### 6.2 Thiếu gì (gap)

| # | Gap | Mức ưu tiên | Effort | Blocked by |
|---|-----|-------------|--------|------------|
| **G1** | **Move chat từ website → backend Odoo** | 🔴 P0 | 1-2h | — |
| **G2** | **Modes toggle (staff/client)** trong chat | 🔴 P0 | 1h | G1 |
| **G3** | **FastAPI middleware service** skeleton | 🔴 P0 | Day 3 (4h) | — |
| **G4** | **Ingestion pipeline** (chunk 500-1000 + embed + store) | 🔴 P0 | Day 3 (4h) | G3 |
| **G5** | **Vector store** (pgvector hoặc Chroma) | 🔴 P0 | Day 3 (2h) | G3 |
| **G6** | **`bill.of.lading` model** + `bl.field` confidence | 🔴 P0 | Day 5 (3h) | — |
| **G7** | **B/L vision endpoint** + 5 sample scans | 🔴 P0 | Day 6 (5h) | G3, G6 |
| **G8** | **B/L review form view** (side-by-side + low-conf tag) | 🔴 P0 | Day 6 (3h) | G6 |
| **G9** | **Invoice OCR config** (Enterprise `account_invoice_extract`) | 🟡 P1 (cut-able) | 30min | Enterprise license |
| **G10** | **Google Calendar OAuth** cho 2 demo users | 🟡 P1 | Day 7 (1h) | Google account |
| **G11** | **Appointment types** (Sales 30m, Onboarding 60m, GMT+10) | 🟡 P1 | Day 7 (1h) | Enterprise `appointment` |
| **G12** | **Real LLM integration test** (khi có API key) | 🟢 P2 | 30min | ANTHROPIC_API_KEY |
| **G13** | **Source citation linking** (chips → Odoo docs) | 🟢 P2 | 2h | G3 |

### 6.3 Vấn đề cụ thể cần fix ngay

**G1 — Chatbot hiện tại là website page, sai use case**:

```python
# controllers/ai_chatbot.py:23 — SAI
@http.route('/steamships/chat', type='http', auth='user', website=True)
def chat_page(self, **kw):
    return request.render('steamships_demo.chat_widget_page', {...})
```

`website=True` = public route render qua `website.layout`. Staff workflow cần **backend menu action** (ir.actions.client hoặc form view), không phải portal page.

**Fix**:
- Xóa route `/steamships/chat` (website=True)
- Xóa template `chat_widget_page` (dùng `website.layout`)
- Xóa `chat_launcher` template (inject vào mọi trang website = rác)
- Bỏ depend `website` khỏi `__manifest__.py`
- Bỏ `web.assets_frontend` assets block
- Tạo `ir.actions.client` hoặc wizard mở chat popup trong Odoo backend
- Chuyển `chat_widget.esm.js` sang `web.assets_backend` (nếu giữ widget)
- Giữ `mock_sops.py` + adapter logic → refactor thành backend service

---

## 7. Dependency map (theo DOCX Day-by-day)

```
Day 1-2 (config + data): KHÔNG CẦN AI
  └─ CRM pipeline, products, pricelists, discount approval

Day 3 (RAG brain):
  G3 (FastAPI skeleton) ──┐
  G4 (ingestion) ────────┼─→ parallel
  G5 (vector store) ─────┘

Day 4 (RAG face):
  G1 (move chat → backend) → G2 (modes toggle) → G13 (source links)
  (có thể làm G1+G2 trước Day 3, vì chỉ là UI restructure)

Day 5 (B/L model):
  G6 (bill.of.lading + bl.field models) → morning
  G9 (invoice OCR config) → afternoon (cut-able)

Day 6 (Vision):
  G3 add /api/extract_bl → G7 (5 sample scans) → G8 (review form)

Day 7 (Booking + rehearsal):
  G10 (Google OAuth) → G11 (appointment types) → demo rehearsal
```

---

## 8. Risks (từ DOCX B8)

| Risk | Mitigation |
|------|------------|
| Enterprise trial expires (15 days) | Start trial Day 1, backup DB nightly |
| AI wrong answer live in demo | Rehearse với exact demo questions; system prompt forces "I don't know" |
| Google OAuth fiddly | Do Day 7 morning, test cả 2 demo users |
| Vision misreads bad scan | Pre-test 5 sample B/Ls; chỉ dùng crumpled nếu works reliably |
| Confidential data questions | "Fake data, production covers residency/security in Phase 2" |
| Internet drops (PNG connectivity) | Record backup video, always |

**Mock mode safety**: UI badge "(MOCK MODE)" → audience biết không phải demo sai khi answer keyword match đơn giản.

---

## 9. Out of scope (Phase 2, từ DOCX A2 "Nice-to-have")

- AI meeting note-taker (transcribe + summarize + check SOPs)
- AI proposal/pitch-deck generator
- AI-assisted data migration từ old systems
- Group-wide accounting consolidation across JVs
- Real PNG tax setup (GST, withholding)
- Production security + per-division access rights
- Real company data migration

---

## 10. References

- DOCX: `docs/steamships-plan.docx` Part A (A2, A4), Part B (B4, B5, B7, B8), Part C (C2)
- Plan MD: `docs/steamships-plan.md` (sections 4, 5, 6)
- Code: `addons/custom/steamships_demo/`
- Architecture: section 2 ở trên
