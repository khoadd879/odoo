# Steamships Demo Flows — End-to-End

> Source: `steamships-plan.docx` Part A (A4), Part B (B2-B6), Part C (C2)
> Demo: 20-25 min, 4 scenes + closing
> Status: 2026-06-15

Mỗi flow map 1-to-1 với 1 scene trong demo. Format: **input → system action → output → demo impact**.

Legend:
- ✅ Code đã có (verified 2026-06-15)
- ⚠️ Code có 1 phần, thiếu phụ thuộc
- ❌ Chưa có

---

## Flow 1 — CRM + Onboarding (Scene 1, 4 phút)

**Problem (DOCX A2 P2/P3)**: client registration bị lost, 3 forms khác nhau, không biết deal ở stage nào.

```
[1] Client mở web onboarding form
       ↓
[2] Điền fields (REQUIRED): company, contact, email, phone, country, industry
    Attach 2 files: registration.pdf, kyc.pdf
       ↓ submit
       ↓
[3] Odoo Website form handler (controller Odoo core)
       ↓
[4] Auto-create:
       ├─ crm.lead                  (stage = "Lead")
       ├─ res.partner (company)
       ├─ ir.attachment (× 2 files) → linked to lead
       ├─ mail.activity             (deadline = +24h, "Check documents")
       └─ assign salesperson       (rule: round-robin theo division)
       ↓
[5] Staff mở Odoo → Steamships → Dashboard
       ↓ thấy lead mới trong pipeline
       ↓ click KYC button → "Start Onboarding" wizard
       ↓
[6] Wizard tạo crm.lead.steamships.onboarding record
       ├─ industry (selection: mining, oil_gas, ...)
       ├─ company_size (sme/mid/large/mnc)
       └─ KYC checklist 8 booleans:
              ipa_cert, tax_id, bank_ref, directors_id,
              pep_check, credit_check, insurance_cert, contract_signed
       ↓
[7] Staff tick từng item → completion_pct auto-compute (%)
       ↓ 100% → action "Mark KYC Complete"
       ↓ review → action "Approve"
       ↓
[8] Chatter log + state chuyển: draft → in_progress → kyc_done → approved
       ↓
[9] CRM lead stage tự động: Lead → Qualified → Onboarding Docs → Quoted
       (sẵn sàng cho Flow 2 báo giá)

Demo impact: "Không còn document nào có thể lost nữa.
            1 form thay vì 3. Full history ai-làm-gì-khi-nào."
```

**Code status**:
- ✅ `models/crm_lead_onboarding.py` — KYC 8 items + completion_pct compute
- ✅ `models/crm_lead_link.py` — `crm.lead` inherits, adds onboarding_id + KYC button
- ✅ `wizards/crm_lead_onboarding_wizard.py` — start onboarding wizard
- ✅ `views/crm_lead_views.xml` — inherit CRM form, add Onboarding tab + KYC stat button
- ❌ **Web form chưa có** (cần `website_form` builder cho `/onboarding` page — G14)

**Khi demo**: workaround tạm thời — tạo lead thủ công từ backend, skip web form (chỉ làm vài giây).

### Flow 1 — Business Workflow Details (từ DOCX B2)

**5 sales pipeline stages** (nguyên văn DOCX, thứ tự bắt buộc):
```
Lead → Qualified → Onboarding Docs → Quoted → Won / Lost
```

**Web form fields** (nguyên văn DOCX B2):
| Field | Type | Required | Note |
|-------|------|----------|------|
| `company_name` | char | ✅ | |
| `contact_person` | char | ✅ | |
| `email` | email | ✅ | |
| `phone` | char | ✅ | |
| `country` | selection | ✅ | default PNG |
| `industry` | **selection** | ✅ | **DOCX values: `Logistics / Property / Hospitality / Joint Venture`** (4 options) — KHÔNG phải mining/oil_gas hiện tại |
| `service_needed` | **selection (multi)** | ❌ | thêm field này vào onboarding model |
| `file_upload` | binary (multiple) | ❌ | unlimited files |

⚠️ **Code mismatch**: `crm.lead.steamships.onboarding.industry` hiện có 8 options (mining, oil_gas, ...) — sai DOCX. Cần fix về 4 options chuẩn.

**Auto-actions khi form submit** (DOCX B2 nguyên văn):
1. Auto-create CRM lead (stage = "Lead")
2. Attach tất cả uploaded files → lead
3. **Auto-assign salesperson** (rule chưa specify — cần implement: round-robin theo division hoặc hard-code demo user)
4. **Auto-create mail.activity** với deadline `now + 24h`, summary = "Check documents within 24 hours"

**Done-when SLA** (DOCX B2):
- ⏱ Form submit → lead visible trong pipeline **< 5 seconds**
- 📋 Chatter log full history (ai-làm-gì-khi-nào)

**Cross-flow hook**: Khi KYC state → `approved`, CRM lead stage tự động chuyển sang `Quoted` (chuẩn bị cho Flow 2). Cần stage transition logic.

---

## Flow 2 — Price List + Quote (Scene 2 phần 2, 2 phút)

**Problem (DOCX A2 P4)**: sales không biết giá phải quote, mỗi team 1 giá, mất tiền + confuse client.

```
[1] Staff → Steamships → Sales → Quotations → New
       ↓
[2] Pick client (res.partner từ Flow 1)
       ↓
[3] Add order lines từ product dropdown:
       ├─ FCL 20ft Lae→POM         (PGK 4,500)
       ├─ FCL 40ft Lae→POM         (PGK 7,800)
       └─ LCL per m³               (PGK 280)
       ↓
[4] Pricelist auto-apply:
       ├─ Standard           (list price, PGK)
       ├─ Contract customer  (-10%, cần approval nếu >10%)
       └─ JV partner         (-15%, cần approval)
       ↓
[5] Thử discount 15% trên 1 line
       ↓ x_discount_pct compute = 15.2%
       ↓
[6] BLOCK tại action_confirm:
       "Discount 15.2% exceeds threshold 10%. Request approval before confirming."
       ↓
[7] Click "Request Approval" button
       ↓
[8] Wizard tạo sale.order.approval.request:
       ├─ order_id, requested_by, requested_date
       ├─ total_discount_pct = 15.2
       ├─ total_discount_amount = PGK 1,250
       └─ reason (text)
       ↓
[9] Manager → Steamships → Sales → Discount Approvals
       ↓ mở pending request
       ↓ nhập review_notes
       ↓ Approve
       ↓
[10] order.x_discount_approved = True
       chatter log: "Discount approval GRANTED. Avg 15.2%."
       ↓
[11] Quay lại order → confirm OK
       ↓ Send by email
       ↓ PDF branded: Steamships logo, PGK currency, payment terms
       ↓ internal margin column HIDDEN trên PDF
       ↓
[12] Chatter log đầy đủ: discount, approve, send

Demo impact: "15 phút quote giờ 90 giây. Discount > 10% phải qua manager.
            8/10 new hire không còn quote sai giá nữa."
```

**Code status**:
- ✅ `models/sale_order_approval.py` — threshold 10%, approval_request, action_confirm block
- ✅ `data/product_data.xml` — products theo 3 divisions
- ✅ `data/product_pricelist_data.xml` — Standard/Contract/JV pricelists
- ✅ `data/res_currency_data.xml` — PGK
- ⚠️ Branded PDF template chưa customize (G15: thêm logo + Steamships colors vào `sale.report_saleorder`)

**Khi demo**: dùng default Odoo PDF (cosmetic only, logic 100% work).

### Flow 2 — Business Workflow Details (từ DOCX B3)

**Product catalog** (DOCX B3 nguyên văn — phải có những service này):
| Service | Division | Pricing model |
|---------|----------|---------------|
| Container FCL 20ft (Lae → POM) | Logistics | per box |
| Container FCL 40ft (Lae → POM) | Logistics | per box |
| LCL per cubic metre | Logistics | per CBM |
| Stevedoring per move | Logistics | per move |
| Warehouse storage per day | Property | per m²/day |
| Office lease per m²/month | Property | per m²/month |

**3 price lists + 2 currencies** (DOCX B3):
| Pricelist | Discount | Currency | Use case |
|-----------|----------|----------|----------|
| Standard | list price | PGK | default |
| Contract customer | -10% | PGK | đã ký hợp đồng |
| JV partner | -15% (cần approval) | PGK | joint venture |
| USD Corporate | FX rate | USD | khách quốc tế |

⚠️ Code hiện có: 3 pricelists (Standard/Contract/JV) + PGK currency. **Cần thêm USD Corporate pricelist** cho khách quốc tế (multinational per A1).

**Discount approval rule** (DOCX B3 nguyên văn):
- Discount **> 10%** → block confirm → require manager approval
- 15% discount demo = show this control feature ("bosses love control features")
- Block point = `action_confirm` (đã có ✅)

**Branded PDF requirements** (DOCX B3):
- ✅ Company name (Steamships Trading)
- ❌ Logo placeholder (G15: png file trong `static/`)
- ❌ Payment terms section (terms_id field)
- ❌ Steamships colors (red/black/yellow = PNG flag)
- ❌ Internal-only field: **profit margin per line** (HIDDEN trên client PDF, SHOW trên internal view)

**Done-when SLA** (DOCX B3):
- ⏱ Pick client + add 3 services + branded PDF + email **< 2 minutes**
- 🚫 15% discount bị block + manager approval popup

**Email flow** (DOCX B3 "email a branded PDF quote"):
- Sale order → action "Send by Email"
- Template auto-attach PDF
- Recipients = `partner_id.email`
- Optional: schedule follow-up activity 3 days sau nếu không reply

---

## Flow 3 — AI Chatbot RAG (Scene 2 phần 1, 6 phút — THE STAR)

**Problem (DOCX A2 P1)**: 8/10 new hire mắc lỗi cơ bản, sales không biết giá 24/7.

> ⚠️ Đây là flow vừa refactor trong G1+G2 (move chat từ website → backend Odoo).

```
[1] Staff (sales rep mới) cần biết giá + docs cho 1 case cụ thể
       ↓
[2] Odoo backend → menu Steamships → AI Assistant → Ask AI
       ↓ (ir.actions.client tag="steamships_ai_chat", KHÔNG phải website page)
       ↓
[3] Chat widget render trong .o_action_manager (Odoo backend area):
       ├─ Header (purple #714B67): "Steamships AI Assistant"
       ├─ Mode toggle (segmented control): [Staff] [Client]
       │     └─ Default: Staff (localStorage persist qua session)
       ├─ Welcome message (mode-aware)
       └─ Log + input + Send button
       ↓
[4] Staff gõ: "A client wants to ship a 20ft container from Lae to POM"
       ↓ nhấn Enter hoặc Send
       ↓
[5] JS POST /steamships/chat/api  (JSON-RPC, auth='user')
       body: {jsonrpc:"2.0", params:{message, mode:"staff"}}
       ↓
[6] Odoo controller chat_api() (Python):
       ├─ Validate mode ∈ {staff, client}
       ├─ Import mock_sops.search_sops(message, top_k=3, visibility=("public","staff"))
       │     │
       │     ├─ Tokenize query lowercase
       │     ├─ Filter SOPs: visibility phù hợp mode
       │     ├─ Score = |query_tokens ∩ (sop_keywords ∪ content_tokens)|
       │     └─ Top 3 sources
       │
       ├─ Mode = STAFF → visibility=("public","staff")  → 12 SOPs match-able
       │ Mode = CLIENT → visibility=("public",)         → 3 SOPs match-able
       │
       ├─ MOCK_MODE = (no ANTHROPIC_API_KEY env)
       │   └─ _mock_reply:
       │       ├─ Nếu sources = []: trả "I'm a demo assistant... Try asking..."
       │       └─ Nếu sources có: trả "[MOCK - STAFF] Based on **{title}**:\n\n{content}\n\n_Source: ..._"
       │
       └─ MOCK_MODE = False (real Claude API):
           └─ _real_llm_reply:
               ├─ Build system prompt (mode-aware):
               │   STAFF: "You are answering a Steamships staff member.
               │           You may share internal SOPs and price list data."
               │   CLIENT: "You are answering a Steamships client (external).
               │            DO NOT reveal internal SOPs, internal policies,
               │            or exact internal prices. If asked, politely
               │            redirect to the sales team."
               ├─ Context = "\n\n".join(f"[{s.title}]\n{s.content}" for s in sources)
               ├─ anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
               ├─ claude.messages.create(model="claude-haiku-4-5-20251001", max_tokens=512)
               └─ Return resp.content[0].text
       ↓
[7] Optional: log to chatter nếu conversation_id passed
       ├─ Format: "crm.lead,42" → post body "[AI Chat (staff)] Q: ...\nA: ..."
       └─ Best effort, không block reply nếu fail
       ↓
[8] Response: {reply, sources, mode, mock_mode}
       ↓
[9] JS render trong chat log:
       ├─ User bubble (purple bg, right-aligned)
       ├─ Bot bubble (white bg, left-aligned, text wraps)
       └─ Sources line: "Sources: FCL 20ft... | KYC Checklist..."
       ↓
[10] MOCK MODE badge hiện trên header (nếu mock_mode=True)
       ↓
[11] Demo trick — hỏi câu NGOÀI knowledge base:
        "What is the CEO's phone number?"
       ↓
   [12] search_sops → no match → sources=[]
       ↓
   [13] _mock_reply trả:
        "[MOCK - STAFF] I'm a demo assistant... Try asking 'FCL 20ft price?'"
       ↓
   [14] Staff nói: "Bot never guesses. Đó là cách nó bảo vệ new hire khỏi sai sót."

Demo impact: "8/10 nhân viên mới có answer đúng 24/7, có source chứng minh.
            Không guess — khi không biết, nói thẳng không biết."
```

**Visibility mapping** (15 SOPs, mock_sops.py):
- `staff` (12): FCL/LCL/stevedoring/tug/lease/warehouse/hotel/suite pricing, discount threshold, currency, conference
- `public` (3): KYC checklist, customs process, branches coverage

→ Client hỏi "FCL 20ft price" → `search_sops(visibility=("public",))` filter ra → fallback "contact sales team" (đúng DOCX: *"must NOT reveal internal prices or SOPs"*).

**Code status** (G1+G2 done 2026-06-15):
- ✅ `controllers/ai_chatbot.py` — JSON-RPC endpoint, mode param, adapter (mock/real)
- ✅ `mock_sops.py` — 15 SOPs với `visibility`, mode-aware search
- ✅ `views/chat_widget_views.xml` — `ir.actions.client` tag=`steamships_ai_chat`
- ✅ `views/menu_views.xml` — menu Steamships → AI Assistant → Ask AI
- ✅ `static/src/js/chat_widget.esm.js` — backend render, mode toggle, localStorage
- ✅ `__manifest__.py` — bỏ `website` depend, JS assets → `web.assets_backend`

**Còn thiếu cho Day 3-4 (production-quality)**:
- ❌ G3: FastAPI middleware thật (hiện tại mock_sops chạy in-process trong Odoo)
- ❌ G4: Ingestion pipeline (chunks 500-1000 chars + overlap 100 + embeddings)
- ❌ G5: Vector store (pgvector Odoo 18 native, hoặc Chroma)
- ❌ G13: Source citation linking (chips hiện là text, cần link tới Odoo `ir.attachment` / `documents.document`)

**Mock safety**: UI badge "MOCK MODE" → audience biết không phải demo sai khi answer keyword match đơn giản.

### Flow 3 — Business Workflow Details (từ DOCX B4)

**Retrieval configuration** (DOCX B4 nguyên văn):
- **Top-K chunks** = **5** (hiện code dùng 3 — sai DOCX, cần fix)
- Chunk size: **500-1,000 chars** với overlap ~100 chars
- Vector store: pgvector (Odoo 18 native) hoặc Chroma
- Embeddings: Anthropic `voyage-3` (khi real API) hoặc mock hash (no key)

**10-20 sample documents** (DOCX B1, B4) — cần ingest:
| Type | Count | Examples |
|------|-------|----------|
| SOPs | 10-15 | SOP-SHIP-004 (container booking docs), SOP-LEASE-002 (lease terms), SOP-HOTEL-001 (group booking) |
| Price list | 1 | export từ Odoo product.pricelist |
| Onboarding checklist | 1 | KYC requirements (đã có trong mock_sops) |
| FAQ | 1-2 | common client questions |
| Company policy | 1-2 | approval rules, working hours |

**Source citation format** (DOCX B4 nguyên văn):
```
Source: SOP-SHIP-004
```
- Code hiện trả `sources: ["FCL 20ft Container - Standard Pricing"]` (title)
- DOCX muốn format `Source: SOP-SHIP-004` (sop_id)
- Cần đổi: trả `s['id']` thay vì `s['title']` (hoặc cả hai)

**"I don't know" fallback** (DOCX B4 nguyên văn):
> *"If the answer is not in the documents, say you do not know **and name a person/team to ask**."*

Code hiện tại `_mock_reply` chỉ trả "Try asking...". Cần bổ sung:
```
"I don't know. Please ask the Sales Operations team (sales.ops@steamships.com.pg)."
```

**Real LLM system prompt** (DOCX B4 nguyên văn):
```
Answer ONLY from the provided documents. If the answer is not in the documents,
say you do not know and name a person/team to ask. Always cite your sources.
```
- Code hiện tại có prompt này ✅ nhưng thiếu phần "name a person/team" instruction

**Demo exact question** (DOCX C2 nguyên văn):
> *"A client wants to ship a 20ft container from Lae to Port Moresby — what do I quote and what documents do I need?"*

Expected answer:
- Price: PGK 4,500
- Documents: KYC checklist (8 items)
- Source: SOP-SHIP-004 (or mock_sops id `sop-001`)

**Done-when SLA** (DOCX B4):
- ✅ Câu hỏi trong KB → trả price + docs + source names
- ✅ Câu hỏi ngoài KB → "I don't know" honest reply

**UI path** (DOCX B4):
> *"Easiest path: a standalone web page (simple HTML/JS) styled with company colours, **or embed it in Odoo via an iframe / Odoo's website builder**."*

- Chọn option 2: **embed as Odoo backend client action** (đã làm trong G1)
- Company colors: Steamships = PNG flag (red #CE1126, black #000, yellow #FCD116) + theme purple #714B67 hiện tại

---

## Flow 4 — AI Document Reader (Scene 4, 6 phút — THE MAGIC TRICK)

**Problem (DOCX A2 P6)**: shipping document-heavy, staff gõ tay chậm + lỗi.

### 4a — Supplier Invoice OCR (cut-able, chỉ config)

```
[1] Staff Accounting → upload supplier_invoice.pdf
       ↓ (vào Documents app hoặc kéo thả vào vendor bill)
       ↓
[2] Odoo Enterprise `account_invoice_extract` (IAP service)
       ↓ gọi OCR API tự động
       ↓
[3] Auto-create account.move (vendor bill) DRAFT:
       ├─ partner_id         (vendor name recognized)
       ├─ invoice_date
       ├─ amount_total
       └─ line items
       ↓
[4] Staff mở bill → review fields → Post

Demo impact (30s): "Built-in OCR, 0 custom code"
```

**Code status**: ❌ CHƯA CÓ (cần Enterprise license + IAP credits, cut đầu tiên nếu trễ — DOCX B7).

### 4b — Bill of Lading Vision (custom, THE WOW)

```
[1] Staff shipping nhận bl_scan_crumpled.jpg từ email client
       ↓
[2] Odoo menu: Steamships → B/L Documents → New
       ↓ upload file → ir.attachment (datas = base64)
       ↓ click button "Extract with AI"
       ↓
[3] Frontend POST /api/extract_bl (FastAPI middleware, future)
       body: {bl_id, image_b64, filename}
       ↓
[4] FastAPI service (Day 6):
       ├─ Load Claude vision model
       ├─ Build prompt:
       │   "You are extracting data from a Bill of Lading scan.
       │    Return STRICT JSON only, no commentary:
       │    {
       │      bl_number, shipper, consignee, notify_party,
       │      vessel_name, voyage_number, container_numbers[],
       │      port_loading, port_discharge, cargo_description,
       │      weight_kg, bl_date,
       │      confidence: {<field>: high|medium|low, ...}
       │    }
       │    If illegible, value=null, confidence=low."
       ├─ Send image + prompt
       └─ Parse JSON response
       ↓
[5] Odoo JSON-RPC write:
       ├─ bill.of.lading.create({
       │     bl_number, shipper, ..., state='pending_review',
       │     attachment_id, ...
       │   })
       └─ bill.of.lading.field.create([...]):
              [{bl_id, field_name:"shipper", field_value:"...", confidence:"high"},
               {bl_id, field_name:"consignee", field_value:"...", confidence:"medium"},
               ...]
       ↓
[6] Staff mở review form (split view):
       ┌─────────────────────┬──────────────────────┐
       │  Extracted fields   │  Original scan       │
       │  ───────────────    │  (ir.attachment)     │
       │  BL#: PNG-2026-0042 │                      │
       │  Shipper: Acme Co   │   [image preview]    │
       │  Consignee: ⚠ low  │                      │
       │   "Please check"    │                      │
       │  Vessel: ...        │                      │
       │  Containers: ...    │                      │
       │  ...                │                      │
       │                     │                      │
       │  [Re-extract] [Approve]                    │
       └─────────────────────┴──────────────────────┘
       Low-conf fields có:
       - Red border
       - "⚠ please check" badge
       - Border highlight
       ↓
[7] Staff sửa field sai
       ↓ click Approve
       ↓
[8] bill.of.lading.state = 'approved'
       chatter log: "B/L PNG-2026-0042 approved by <user>"

Demo impact: "12 phút gõ tay + nhiều lỗi → 20s AI + 1 click human check.
            Demo dùng crumpled scan để AI vẫn đọc đúng → wow moment."
```

**Code status**: ❌ Hoàn toàn chưa có. Cần build:
- ❌ G6: `models/bill_of_lading.py` + `models/bill_of_lading_field.py` (13 fields + confidence child)
- ❌ G7: FastAPI `/api/extract_bl` + 5 sample scans trong `middleware/data/sample_bls/`
- ❌ G8: B/L review form view (split layout + low-conf highlight)

**5 sample scans** (chuẩn bị sẵn):
1. `bl_clean_001.jpg` — clean scan, mọi field high
2. `bl_clean_002.png` — clean, multi-container
3. `bl_skewed_003.jpg` — nghiêng 15°
4. `bl_crumpled_004.jpg` — **crumpled/skewed, THE WOW**
5. `bl_partial_005.jpg` — bottom cut off, 1-2 fields low conf

Mỗi file có `.json` pre-baked (mock vision mode).

### Flow 4b — Business Workflow Details (từ DOCX B5)

**B/L fields** (DOCX B5 nguyên văn, 13 fields):
| # | Field | Type | Note |
|---|-------|------|------|
| 1 | bl_number | char | indexed |
| 2 | shipper | char | |
| 3 | consignee | char | |
| 4 | notify_party | char | |
| 5 | vessel_name | char | |
| 6 | voyage_number | char | |
| 7 | container_number(s) | text/One2many | newline-separated |
| 8 | port_of_loading | char | |
| 9 | port_of_discharge | char | |
| 10 | cargo_description | text | |
| 11 | weight | float | kg or MT |
| 12 | date | date | |
| 13 | status | selection | Draft / Pending Review / Approved |
| + | file_attachment | Many2one(ir.attachment) | original scan |

**Confidence per field** (DOCX B5):
- 3 levels: `high / medium / low`
- Low-confidence fields → highlight (red border, "⚠ please check" badge)
- Stored as child model `bill.of.lading.field` (1 B/L → 13 field records)

**Vision prompt** (nguyên văn DOCX B5):
> *"a prompt asking for a strict JSON answer matching the fields above, plus a confidence score (high/medium/low) per field"*

**Done-when SLA** (DOCX B5):
- ⏱ Upload B/L photo → filled record **< 30 seconds**
- ⏱ 1-click human approval
- 📊 Demo comparison: **manual typing ≈ 12 minutes với errors** vs **AI ≈ 20 seconds + human check**

**3-5 sample scans** (DOCX B5 nguyên văn):
> *"Prepare 3-5 sample B/L scans of mixed quality for the demo — include one slightly crumpled/skewed photo."*

- 1 clean (baseline) + 1 multi-container + 1 skewed + **1 crumpled/skewed (THE WOW)** + 1 partial
- Mỗi file có `.json` pre-baked cho mock mode

**4a Invoice OCR** (DOCX B5 "no code needed"):
- Accounting → Settings → Document Digitisation → ON
- Upload 2-3 sample supplier invoices
- Odoo auto-tạo DRAFT bill với vendor/date/amounts pre-filled
- Human review + Post
- ⚠️ Cần Enterprise license (`account_invoice_extract` module)

## Flow 5 — Smart Booking (Scene 3, 3 phút)

**Problem (DOCX A2 P5)**: schedule qua time zones = nhiều email qua lại.

```
[1] Sales rep gửi booking link:
       https://odoo.steamships.com.pg/appointment/sales-call
       ↓
[2] Client Singapore mở link
       ↓ browser timezone = Asia/Singapore (auto-detect)
       ↓
[3] Odoo Appointment app render page:
       ├─ Working hours: PNG office 08:00-17:00 GMT+10
       ├─ Convert to client TZ: 06:00-15:00 SGT
       ├─ Show slots (Tue 16 Jun 09:00 SGT, 10:00 SGT, ...)
       └─ 2 types: Sales Call 30min, Client Onboarding 60min
       ↓
[4] Client pick slot → form (name, email, phone, notes) → Confirm
       ↓
[5] Odoo auto-execute:
       ├─ Create calendar.event
       │   ├─ name: "Sales Call - <Client Co>"
       │   ├─ start, stop, partner_ids
       │   └─ alarm_ids (reminder)
       ├─ Google Calendar sync (OAuth connector)
       │   └─ Event xuất hiện trong sales rep's Google Calendar
       ├─ Send confirmation email (template)
       └─ Post chatter on crm.lead: "Meeting booked Tue 16 Jun 16:00 GMT+10"
       ↓
[6] Sales rep thấy:
       ├─ Google Calendar (mobile + desktop)
       └─ Odoo CRM (lead chatter log)

Demo impact: "0 email để schedule 1 meeting. Timezone auto-detect.
            Mọi meeting tự động ghi vào client file."
```

**Code status**: ❌ Chưa có. Cần:
- ❌ G11: Enterprise `appointment` module install + 2 appointment types config
- ❌ G10: Google Calendar OAuth cho 2 demo users (DOCX cảnh báo: làm Day 7 morning, không phải 1h trước demo)

### Flow 5 — Business Workflow Details (từ DOCX B6)

**2 appointment types** (DOCX B6 nguyên văn):
| Type | Duration | Use case |
|------|----------|----------|
| Sales Call | 30 min | initial qualification |
| Client Onboarding | 60 min | deep-dive, requirements gathering |

**Working hours** (DOCX B6 nguyên văn):
- **GMT+10** (PNG time, Port Moresby timezone)
- Office hours: 08:00-17:00 local
- Auto-convert to visitor's timezone (Odoo native)

**Timezone test** (DOCX B6 nguyên văn):
> *"test it by switching your browser/computer time zone to Singapore or Sydney"*

Demo flow:
- Browser TZ = Asia/Singapore → show 06:00-15:00 SGT slots
- Browser TZ = Australia/Sydney → show 08:00-17:00 AEST slots (PNG 06:00-15:00)
- Cùng 1 calendar, khác display

**Auto-actions sau khi book** (DOCX B6):
1. Create `calendar.event` với partner_ids
2. **Sync sang Google Calendar** (sales rep's account, OAuth connector)
3. Send **confirmation email** (template mặc định hoặc custom)
4. **Auto-log as meeting on CRM record** (chatter post: "Meeting booked Tue 16 Jun 16:00 GMT+10")

**Done-when SLA** (DOCX B6):
- ✅ Browser Singapore → show Singapore times
- ✅ Booking → event in Google Calendar
- ✅ Meeting tự động xuất hiện trên CRM record

**Risk** (DOCX B8):
> *"Google OAuth setup is fiddly. Do it early on Day 7 morning, not 1 hour before the demo. Test with both demo users."*

---

## Tổng hợp tiến độ

| Flow | DOCX | Code status | Effort remaining | Risk |
|------|------|-------------|------------------|------|
| 1. CRM + Onboarding | Scene 1 (4 min) | 🟡 80% | G14: web form (1h) | Thấp |
| 2. Price List + Quote | Scene 2.2 (2 min) | 🟡 85% | G15: branded PDF (1h) | Thấp |
| 3. AI Chatbot RAG | Scene 2.1 (6 min) | 🟢 G1+G2 done, 🟡 50% overall | G3-G5, G13 (Day 3-4) | Trung bình |
| 4a. Invoice OCR | Scene 4 quick | 🔴 0% | G9 (30min, cut-able) | Cần Enterprise |
| 4b. B/L Vision | Scene 4 (6 min) | 🔴 0% | G6-G8 (Day 5-6) | Trung bình |
| 5. Smart Booking | Scene 3 (3 min) | 🔴 0% | G10-G11 (Day 7) | Google OAuth fiddly |

**Critical path** (theo DOCX Day 1-7):
- Day 1-2: Flow 1 + 2 (config + data) → có thể demo được 70%
- Day 3-4: Flow 3 (FastAPI + chat backend) → demo THE STAR
- Day 5-6: Flow 4b (B/L Vision) → demo THE MAGIC
- Day 7: Flow 5 (Booking) + rehearsal

**Cut order** (DOCX B7) nếu trễ:
1. Client-mode chatbot toggle (đã làm rồi, dễ drop)
2. Invoice OCR part
3. Simplify B/L review screen (bỏ low-conf highlight)

**KHÔNG BAO GIỜ cut**: Feature 1, 2, staff chatbot, B/L reader.

---

## Cross-flow integration

**Cùng 1 client xuyên suốt demo**:
```
Scene 1: client Acme Co → onboarding form → lead created
                                              ↓
Scene 2.1: AI chatbot hỏi "FCL 20ft price Lae→POM"
                                              ↓ (answer: PGK 4,500 + SOP-SHIP-004)
Scene 2.2: pick client Acme Co → add 3 services → quote
                                              ↓
Scene 3: gửi booking link cho Acme → book sales call
                                              ↓
Scene 4: nhận B/L cho Acme shipment → upload → AI extract → approve

Toàn bộ 4 scene dùng CÙNG 1 client → audience thấy end-to-end
```

**Cùng 1 chatter thread**:
- Mỗi action (AI chat, KYC approve, discount approval, B/L approve) đều ghi chatter log trên crm.lead tương ứng
- Khi audience hỏi "audit trail đâu?" → mở chatter, thấy timeline đầy đủ

---

## Demo Bookends (DOCX C2 Opening + Closing)

### Opening (2 phút)

**Script nguyên văn (DOCX C2)**:
> *"You told us about lost client documents, three different onboarding forms, sales teams unsure what to quote, and new hires making basic errors. In the next 20 minutes we will show you one system, built in one week, that fixes every one of those — live, not slides."*

**Mục đích**:
- Map 4 problems Head of Strategy đã nói (P2 lost docs, P3 3 forms, P4 quote confusion, P1 new hire errors) → set audience mindset
- Promise: 20 min, 1 system, 1 week, live not slides
- Tone: confidence + honesty (no slides, live demo)

### Closing (3 phút) — Phase 2 slide

**4 Phase 2 features** (DOCX C2 nguyên văn):
| # | Phase 2 feature | Note |
|---|----------------|------|
| 1 | **AI meeting note-taker** | join meetings, write summaries, find follow-ups, check SOPs (consent policy required) |
| 2 | **AI proposal / pitch-deck generator** | |
| 3 | **AI-assisted migration** of old data into new system | |
| 4 | **Group-wide accounting consolidation** across JVs | |

**Honest-limits statement** (DOCX C2 nguyên văn):
> *"What you saw today is a prototype built in 7 days on sample data. Production needs security, access rights per division, real data migration, and PNG tax setup — that is the Phase 2 program."*

**The ask** (DOCX C2 nguyên văn):
> *"If this direction is right, the next step is a **scoping workshop** with each division to plan Phase 1 of the real rollout."*

→ Demo KHÔNG có ask = chỉ là show. **Always end with ask.**

---

## Success Criteria (DOCX C5)

Demo thành công khi đạt **4 outcomes** (nguyên văn):

| # | Outcome | Measure |
|---|---------|---------|
| 1 | Head of Strategy nói "I need this" / "When can we start?" | qualitative |
| 2 | ≥1 scene có **audible reaction** (thường Scene 2 hoặc 4) | qualitative |
| 3 | Audience không confused demo vs Phase 2 (honesty = trust point) | qualitative |
| 4 | **Leave với date cho scoping workshop** | quantitative (calendar invite sent) |

---

## Demo Day Checklist (DOCX C4)

| # | Item | Note |
|---|------|------|
| 1 | Rehearse full demo **≥ 2 lần** trước 1 ngày | với exact questions + files |
| 2 | Record **backup video** của full demo | PNG connectivity = unreliable, always have backup |
| 3 | Seed PNG data với **real route names**: Lae, Port Moresby, **Madang, Rabaul** | làm demo cảm giác "their company" |
| 4 | Phase 2 slide ready | 4 features trên |
| 5 | Honest-limits answers ready | fake data, no security hardening yet |
| 6 | Mỗi scene giữ đúng thời gian | nếu break → switch backup video, đừng apologize 2 lần |
| 7 | **End with ask** (scoping workshop) | demo không có ask = just a show |

**PNG route names gap** (C4 #3):
- Code hiện tại `data/branch_data.xml`: POM, Lae, Motukea, Daru
- **DOCX yêu cầu thêm**: **Madang, Rabaul** (real PNG ports per A1)
- Action: thêm 2 branches vào data (G16, 15 phút)

**SOP names với format `SOP-{DIVISION}-{NUMBER}`** (B4):
- DOCX ví dụ: `SOP-SHIP-004`, `SOP-LEASE-002`, `SOP-HOTEL-001`
- Code hiện tại: `sop-001` ... `sop-015` (generic ID, không match format)
- Action: đổi ID theo format `SOP-SHIP-001`, `SOP-LEASE-001` etc (G17, 15 phút)

---

## Cross-flow Workflow Details (bổ sung)

### Stage transition logic (Flow 1 → 2)

Khi KYC state = `approved` (Flow 1 end), CRM lead stage **tự động** chuyển:
```
Qualified → Onboarding Docs → Quoted
```
Cần code override `crm.lead.stage_id` write khi `crm.lead.steamships.onboarding.onboarding_state = 'approved'`.

### Multi-currency (Flow 2)

- Default: **PGK** (PNG Kina)
- Alternative: **USD Corporate** (cho khách quốc tế)
- FX rate: reviewed quarterly (per SOP-013 mock)
- Demo: show 1 quote PGK, 1 quote USD cùng 1 service

### 24-hour follow-up (Flow 1 cross-flow)

- `mail.activity` với `date_deadline = create_date + 24h`
- Activity type: "Check documents within 24 hours"
- Assigned to: lead.user_id (salesperson)
- Nếu quá 24h chưa check → activity due, hiện red badge trên lead

### Audit trail pattern (all flows)

Mỗi significant action log vào chatter:
| Action | Log format |
|--------|-----------|
| Onboarding state change | "Onboarding state: draft → in_progress (by <user>)" |
| KYC approve | "Onboarding APPROVED. KYC 100%. Ready to quote." |
| Discount request | "Discount approval requested: 15.2% (PGK 1,250). Reason: ..." |
| Discount approve | "Discount approval GRANTED. Avg 15.2%." (manager name auto) |
| AI chat | "[AI Chat (staff)] Q: ...\nA: ..." |
| B/L approve | "B/L PNG-2026-0042 approved by <user>" |
| Calendar booking | "Meeting booked Tue 16 Jun 16:00 GMT+10 with <partner>" |

→ Khi audience hỏi "audit trail đâu?" → mở bất kỳ crm.lead → chatter thấy full timeline.

## References

- DOCX: `docs/steamships-plan.docx`
  - Part A (A2 problems, A4 5 features)
  - Part B (B1 setup, B2-B6 features, B7 timetable, B8 risks)
  - Part C (C1 golden rule, C2 demo script, C3 feelings, C4 checklist, C5 success)
- Plan MD: `docs/steamships-plan.md`
- AI architecture: `docs/ai-architecture-gap.md`
- Code: `addons/custom/steamships_demo/`
- Tasks: TaskList #1-8

## Bổ sung từ re-read lần 2 (2026-06-15)

Re-read toàn bộ DOCX lần 2 catch các business workflow details bị miss:

| Phần | Trước | Sau bổ sung |
|------|-------|-------------|
| Flow 1 | diagram chung | + 5 stages nguyên văn, industry 4 options (Logistics/Property/Hospitality/JV), 24h activity, < 5s SLA, KYC auto stage transition |
| Flow 2 | diagram chung | + 6 service examples, USD Corporate pricelist, 15% block demo, profit margin internal, < 2min SLA, email flow |
| Flow 3 | G1+G2 detail | + top-5 chunks (code đang 3), "Source: SOP-XXX" format, "name a person/team" fallback, exact demo question |
| Flow 4b | high-level | + 13 B/L fields table, 3 confidence levels, 12min vs 20s comparison, vision prompt nguyên văn |
| Flow 5 | high-level | + GMT+10 working hours, Asia/Singapore test, 2 appointment types detail, 4 auto-actions |
| Bookends | ❌ | + Opening script + Closing Phase 2 slide (4 features) + scoping workshop ask |
| Success | ❌ | + 4 outcomes (C5 nguyên văn) |
| Checklist | ❌ | + 7 items (C4) + PNG route names gap (Madang, Rabaul) + SOP naming format gap |
| Cross-flow | 2 paragraphs | + Stage transition logic + multi-currency PGK/USD + 24h follow-up + audit trail pattern (7 actions) |
