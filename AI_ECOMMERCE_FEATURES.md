# ODOO — Tính năng thực sự có (ngoài Ecommerce) + AI Ecosystem

Cập nhật: 2026-06-09 · Stack dự án: Odoo 18 CE Docker tại `/home/khoa/Company/odoo` (DB `company20_vn`, port 8069)

Mục đích: tổng hợp các module/tính năng hay, đã có sẵn (CE/EE/OCA) hoặc do cộng đồng build — kèm link GitHub/apps.odoo.com để bạn mở đọc trực tiếp. Bao gồm 4 nhóm: (1) AI/LLM trong Odoo, (2) Orchestrator/Agent, (3) MCP bridge, (4) Tính năng OCA ngoài ecommerce.

---

## 1) AI / LLM trong Odoo — tổng quan

Có 3 lớp:

- **Lớp provider**: module adapter cho từng hãng (OpenAI, Anthropic, Mistral, Ollama, Replicate, FAL.ai, Letta, LiteLLM)
- **Lớp core**: unified API `llm.generate()`, threading, knowledge/RAG, tools (function calling), assistants
- **Lớp app**: chat widget, email composer, invoice OCR, knowledge base, training data

### ⭐ apexive/odoo-llm — framework AI full-stack cho Odoo (203★)
**Best of breed.** Repo: https://github.com/apexive/odoo-llm

33 modules, chia theo nhóm:

| Module | Vai trò |
|---|---|
| `llm` | Core: model registry, unified `generate()` API, embeddings |
| `llm_openai` / `llm_anthropic` / `llm_mistral` / `llm_ollama` / `llm_letta` / `llm_replicate` / `llm_fal_ai` | Provider adapters (mỗi hãng 1 module) |
| `llm_thread` | "Easy AI Chat" — chat widget integrated với mail system, real-time streaming, multimodal |
| `llm_assistant` | Assistant config (role, goal, tools) + prompt template management |
| `llm_tool` | Function calling — LLM gọi lại Odoo methods |
| `llm_knowledge` | RAG pipeline: chunking + embedding, resource management |
| `llm_knowledge_automation` | Tự động re-embed khi record thay đổi |
| `llm_pgvector` / `llm_qdrant` / `llm_chroma` | Vector store backends |
| `llm_knowledge_llama` / `llm_knowledge_mistral` | Local LLM cho embedding |
| `llm_mcp_server` | **Expose Odoo tools qua MCP** cho Claude Desktop / Letta |
| `llm_tool_account` / `llm_tool_website` / `llm_tool_knowledge` / `llm_tool_ocr_mistral` / `llm_tool_mis_builder` / `llm_tool_demo` | Tools theo domain (accounting, website, knowledge, OCR) |
| `llm_generate_job` | Queue/async generation qua `queue_job` |
| `llm_training` | Tạo training data từ records (fine-tune workflow) |
| `llm_store` / `llm_document_page` | Document knowledge source |
| `account_invoice_import_llm` | Import hóa đơn từ PDF/ảnh qua OCR+LLM |
| `web_json_editor` | Devtool edit JSON field trong UI |

Highlights từ README:
- PostgreSQL advisory locking → không bị race condition khi generate đồng thời
- `llm_role` indexed → query messages nhanh hơn 10×
- MCP 2025-06-18 protocol + JSON-RPC 2.0
- Hỗ trợ LiteLLM → tương thích mọi provider có OpenAI-compatible API

**Branch**: hiện tại active là `16.0-pr` (đang port lên 18/19). Check trước khi dùng.

### OCA/ai (36★) — chính thức từ OCA
**Repo**: https://github.com/OCA/ai · License: AGPL-3.0

7 modules hiện tại (trên main, branch 19.0 đang empty):

| Module | Vai trò |
|---|---|
| `ai_oca_bridge` | Core bridge giữa OCA AI + Odoo core |
| `ai_oca_bridge_chatter` | AI trong chatter (suggest reply, summarize thread) |
| `ai_oca_bridge_document_page` | Knowledge base từ `document_page` |
| `ai_oca_bridge_extra_parameters` | Inject extra params vào LLM call |
| `ai_oca_native_generate_ollama` | Native Ollama provider (không qua OpenAI API) |

→ Đây là lựa chọn "official" cho AI features, sẽ có maintainer lâu dài, merge vào OCB.

### vertelab/odoo-ai — "AI Orchestration for Odoo" (26★)
**Repo**: https://github.com/vertelab/odoo-ai · License: AGPL-3.0

Tuy chỉ 26★ nhưng **repo lớn 40MB** → chắc chứa nhiều code nặng.

| Module | Vai trò |
|---|---|
| `ai_agent` | AI agent core (gần "orchestrator" nhất trong Odoo) |
| `ai_agent_hr` | HR-specific agent (recruitment, leave) |
| `ai_agent_mcp` | Agent expose qua MCP |
| `ai_agent_pgvector` | Agent dùng pgvector làm memory |
| `ai_agent_trend` | Trend analysis agent |
| `ai_mail_e_avrop` | Swedish e-Avrop procurement integration |

### AugeTec/odoo_ai_agents (20★) — gọn, dễ đọc
**Repo**: https://github.com/AugeTec/odoo_ai_agents · License: GPL-3.0

- OpenAI-compatible interface
- Agent config (system prompt, tools)
- Chat widget từ conversation
- Roadmap: document processing, CRM integration

→ Code base nhỏ (99KB) → dễ fork & modify nếu muốn hiểu sâu pattern.

### thespino/odoogpt (25★) — cũ nhưng đơn giản
**Repo**: https://github.com/thespino/odoogpt · License: GPL-3.0

- Tích hợp OpenAI/GPT từ thời Odoo 14
- Code base 926KB, dễ hack
- Phù hợp nếu chỉ cần "ChatGPT trong Odoo" đơn giản, không cần full framework

### MCP server độc lập (quan trọng nếu dùng Claude/Cursor)
**ivnvxd/mcp-server-odoo (310★)** — https://github.com/ivnvxd/mcp-server-odoo · MPL-2.0

- MCP server để Claude/Cursor/LangChain/LlamaIndex gọi thẳng vào Odoo XML-RPC/JSON-RPC
- Features: search, create, update, delete records; count, group_by aggregation, model introspection
- **YOLO mode** cho dev/test nhanh
- Production-grade: install thêm module `mcp_server` (https://apps.odoo.com/apps/modules/19.0/mcp_server) có ACL/permission check
- 1029KB, update liên tục (gần nhất 2026-06-09)

### Cộng đồng khác
- **MFYDev/odoo-expert (94★)** — RAG trên Odoo documentation
- **marcfargas/odoo-toolbox (34★)** — TypeScript SDK + MCP server cho AI agents (CI-tested)
- **yourtechtribe/mcp-odoo-for-finance (14★)** — MCP server chuyên finance
- **PayDece/nanoclaw-odoo-erp-cfo (9★)** — AI CFO agent
- **arunrajiah/odoopilot (14★)** — Self-hosted AI assistant, dùng Odoo mà không cần login UI
- **Shamlan321/OdooSense_V2 (16★)** — Conversational AI cho Odoo

---

## 2) Orchestrator / Agent thực sự là gì trong Odoo?

Trong thế giới Odoo, **"AI orchestrator"** thường có 2 nghĩa:

### (a) AI orchestrator — multi-agent LLM
Module `ai_agent` (vertelab) + `llm_assistant` (apexive) là gần nhất. Pattern:
- Assistant = system prompt + tools + model config
- Thread = cuộc hội thoại (gắn vào record: SO, lead, ticket…)
- Tool = Odoo method được wrap để LLM gọi (vd `sale_order_create`, `partner_search`)
- MCP bridge = expose tool ra ngoài cho agent khác gọi

Không có orchestrator multi-agent "kiểu LangGraph" built-in sẵn. Phải tự build hoặc dùng bên ngoài (Letta, AutoGen) gọi vào Odoo qua MCP.

### (b) Business process orchestrator — workflow
Đây là thứ Odoo mạnh từ lâu:
- `base_automation` (CE, built-in): Automated Actions — trigger theo event (create/write/cron) chạy Python/email
- `queue_job` (OCA/queue, 615★): background job, retry, chunked processing
- **OCA/connector (370★)**: framework cho data integration, multi-channel
  - `connector_prestashop`, `connector_magento`, `connector_amazon` — sync từ sàn TMĐT
  - `connector_interfaces` — ODBC, CSV, file-based
- **OCA/automation (26★)**: rule engine, scheduled actions nâng cao
- `mis_builder` (OCA): Management Information System — KPI templates, flexible reporting
- `auditlog` (OCA/server-ux): full audit trail
- `base_exception` (OCA): exception & validation rules cho mọi workflow

---

## 3) Tính năng OCA hay — ngoài Ecommerce

Đã cài OCA: account-financial-tools, sale-workflow, stock-logistics-workflow, server-ux, server-tools, web, website, e-commerce. Repo `OCA/e-commerce` (193★) có sẵn 12 module nâng cấp website_sale:

### E-commerce (OCA/e-commerce 19.0)
- `website_sale_product_brand` — thương hiệu SP trên shop
- `website_sale_product_minimal_price` — giá sàn, không cho discount sâu hơn
- `website_sale_product_reference_displayed` — hiển internal ref lên frontend
- `website_sale_hide_price` — ẩn giá cho guest/B2B
- `website_sale_order_type` — phân loại đơn (quote/rental/recurring…)
- `website_sale_charge_payment_fee` — thu phí cổng thanh toán
- `website_sale_acquirer_confirm_order` — confirm trước khi payment
- `website_sale_checkout_skip_payment` — checkout 1-click cho admin
- `website_sale_cart_expire` — auto-abandon cart reminder
- `website_sale_stock_picking_policy` — chọn picking policy cho e-commerce
- `website_sale_stock_provisioning_date` — hiển thị ngày giao dự kiến

### Website (OCA/website)
- `website_snippet_country_dropdown` — country picker
- `website_cookie_notice` — GDPR cookie banner
- `website_seo_redirection` — 301 redirect manager
- `website_google_analytics` — GA tracking nâng cao
- `website_mass_mailing` — subscribe từ website

### Server UX (OCA/server-ux) — productivity
- `date_range` — quản lý kỳ báo cáo (tháng/quý/năm tài chính)
- `base_technical_user` — impersonate user để debug
- `multi_step_wizard` — wizard nhiều bước
- `announcement` / `banner` — system notification trong UI
- `mass_mailing_custom_unsubscribe` — opt-out category
- `base_tier_validation` — **multi-level approval workflow** (vd SO > 100tr phải duyệt 2 cấp)

### Server tools (OCA/server-tools)
- `auditlog` — log mọi CRUD lên sensitive model
- `base_exception` — rule validation
- `db_cleanup` — purge obsolete data
- `module_auto_update` — auto-upgrade khi có bản mới (chỉ dev)
- `session_db` — store session trong DB thay vì filesystem

### Account-financial-tools (OCA) — đã cài 6 module
- `account_financial_report` — Balance Sheet, P&L, Cash Flow statement
- `account_move_template` — template cho journal entry
- `account_tax_balance` — báo cáo thuế chi tiết
- `account_tax_closing` — đóng kỳ thuế
- `partner_statement` — sao kê KH
- `report_xlsx` — xuất Excel

### Sale workflow (OCA/sale-workflow)
- `sale_procurement_group_by_line` — mua hàng theo dòng SO
- `sale_stock_picking_blocking` — block picking khi có constraint
- `sale_order_product_recommendation` — **AI-style product recommendation** (cross-sell/upsell dựa trên lịch sử)
- `sale_quotation_number` — tuần tự quote number
- `sale_commercial_partner` — group by commercial entity
- `sale_order_action_invoice_create_hook` — extension point cho invoice creation
- `sale_order_type` — loại SO (quotation/rental/recurring)
- `portal_sale_order_search` — KH tìm SO trên portal

### Stock logistics (OCA/stock-logistics-workflow)
- `stock_no_negative` — chặn stock âm
- `stock_picking_back2draft` — picking về draft
- `stock_move_backdating` — backdate move
- `stock_picking_group_by_partner` — gộp picking theo KH
- `stock_quant_reservation_info` — UI reservation detail

### Sale Recommendation AI (đáng chú ý!)
**`sale_order_product_recommendation`** (OCA/sale-workflow) — dùng thuật toán **collaborative filtering** (kiểu Amazon "customers who bought this also bought") trên lịch sử SO để gợi ý SP khi sales tạo SO mới. Không cần LLM, chạy local, performance OK với 1000+ SO.

---

## 4) Odoo EE 19 vs CE 19 — tính năng "hidden" đáng biết

Nếu sau này muốn nâng cấp lên Enterprise (https://www.odoo.com/pricing):

- **Helpdesk** — ticket + SLA, knowledge base
- **Field Service** — task cho technician, GPS tracking
- **Planning** — shift schedule cho nhân viên
- **Sign** — e-signature tích hợp
- **Approvals** — quy trình duyệt chuyên nghiệp
- **Marketing Automation** — campaign drip email/SMS
- **Studio** — custom app builder không cần code
- **Spreadsheet** — Excel-like trong Odoo
- **Dashboards** — KPI dashboard real-time
- **VoIP** — gọi điện từ CRM
- **WhatsApp Integration** — chat WA với khách

---

## 5) Gợi ý áp dụng vào dự án `company20_vn`

Dựa trên stack hiện tại (CE 18, OCA basic, focus ecommerce + sales), nếu muốn thêm AI:

### Quick win (1-2 ngày)
1. **Install `apexive/odoo-llm`** (nhánh 16.0-pr trước, hoặc port sang 18.0) → có chat widget + 6 provider adapters
2. **Cấu hình Ollama local** (nếu có GPU) hoặc Groq/OpenAI → chat về SO, lead, invoice

### Medium effort (1 tuần)
3. **Build custom `llm_tool_sale_order_summary`** — LLM summarize SO history của KH trước khi sales gọi
4. **Build `llm_tool_email_draft`** — draft email reply từ chatter thread, sales review rồi gửi
5. **Wire `sale_order_product_recommendation`** vào SO form → cross-sell

### Advanced (1 tháng+)
6. **Setup ivnvxd/mcp-server-odoo** → Claude Desktop/Cursor truy cập Odoo qua MCP, bạn chat với data thật
7. **Build multi-agent với vertelab/ai_agent** + Letta/AutoGen bên ngoài → tự động: lead mới → enrich → assign → draft quote
8. **OCR hóa đơn tự động** qua `account_invoice_import_llm` (apexive)

### Risk cần biết
- `apexive/odoo-llm` đang port 18.0/19.0, cần test kỹ
- `vertelab/odoo-ai` chỉ có 1 maintainer → risk abandon
- OCA/ai mới chỉ 7 modules, chưa production-ready cho chatter AI
- LLM call tốn $$/token → cần cache + chỉ gọi khi user action
- GDPR: nếu dùng OpenAI API, dữ liệu KH qua server US → cần consent hoặc dùng local Ollama

---

## Tất cả link (1 click)

### AI/LLM
- apexive/odoo-llm: https://github.com/apexive/odoo-llm (203★)
- OCA/ai: https://github.com/OCA/ai (36★)
- vertelab/odoo-ai: https://github.com/vertelab/odoo-ai (26★)
- AugeTec/odoo_ai_agents: https://github.com/AugeTec/odoo_ai_agents (20★)
- thespino/odoogpt: https://github.com/thespino/odoogpt (25★)
- MFYDev/odoo-expert: https://github.com/MFYDev/odoo-expert (94★)

### MCP
- ivnvxd/mcp-server-odoo: https://github.com/ivnvxd/mcp-server-odoo (310★)
- apexive/llm_mcp_server (module): https://github.com/apexive/odoo-llm/tree/main/llm_mcp_server
- Odoo MCP module (production): https://apps.odoo.com/apps/modules/19.0/mcp_server
- marcfargas/odoo-toolbox: https://github.com/marcfargas/odoo-toolbox (34★)

### Orchestrator/Workflow
- OCA/connector: https://github.com/OCA/connector (370★)
- OCA/queue (queue_job): https://github.com/OCA/queue (615★)
- OCA/automation: https://github.com/OCA/automation (26★)
- OCA/server-ux: https://github.com/OCA/server-ux
- OCA/server-tools: https://github.com/OCA/server-tools

### OCA features hay
- OCA/e-commerce: https://github.com/OCA/e-commerce (193★)
- OCA/sale-workflow (product recommendation): https://github.com/OCA/sale-workflow
- OCA/website: https://github.com/OCA/website
- OCA/account-financial-tools: https://github.com/OCA/account-financial-tools
- OCA/stock-logistics-workflow: https://github.com/OCA/stock-logistics-workflow

### Tài liệu chính thức
- Odoo 19 release notes: https://www.odoo.com/page/odoo-19
- Odoo AI page: https://www.odoo.com/page/ai
- Odoo Apps store: https://apps.odoo.com
- OCA index: https://odoo-community.org/

---

File này: `/home/khoa/Company/odoo/AI_ECOMMERCE_FEATURES.md` — mở bằng `less` hoặc editor bất kỳ.
