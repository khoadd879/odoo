# AI Roadmap cho Odoo 18.0 — Tổng hợp & Đề xuất

**Date:** 2026-06-08
**Scope:** AI Chatbot + RAG + AI Agent cho Odoo 18.0 Community Edition (Docker dev env)
**Báo cáo chi tiết:**
- [ai-research-chatbot.md](./ai-research-chatbot.md) — 568 dòng, chat UI, LLM integration, discuss.channel
- [ai-research-rag.md](./ai-research-rag.md) — 855 dòng, embedding pipeline, vector stores
- [ai-research-agent.md](./ai-research-agent.md) — 660 dòng, tool-use, audit, HITL

---

## 1. TL;DR

**Odoo 18.0 Community Edition không có sẵn bất kỳ AI native nào.** Toàn bộ khả năng AI (chatbot LLM, RAG, agent) phải build custom. Odoo Enterprise AI (`ai.agent`, `ai.composer`, `ai.embedding`) tồn tại nhưng:
- Cloud-only (Odoo Online / Enterprise + IAP credits)
- Không self-host được
- Không dùng được cho community

**OCA ecosystem (2026-06):** Không có OCA/ai repo. Các OCA modules liên quan:
- `OCA/server-tools/queue_job` (18.0) — async job runner, **BẮT BUỘC** cho RAG
- `OCA/website/website_crm_quick_answer` (18.0) — rule-based auto-reply, không phải AI

**Recommended path: tự build, modular, swap LLM provider tự do.**

```
addons/custom/
├── ai_chatbot/         ← chat UI + LLM gateway + bus (Path B từ chatbot report)
├── ai_embedding/       ← ai.embedding model + pgvector + queue_job sync
└── ai_agent/           ← tool dispatcher + audit + HITL + streaming OWL
```

3 module tách biệt vì:
- **Embedding** chạy async, không cần request/response realtime
- **Chatbot** chỉ cần LLM gateway + discuss.channel writeback
- **Agent** cần tool framework + audit + approval

Có thể ship module 1 (chatbot) độc lập. Module 2 (RAG) dùng làm context retrieval cho module 1 + 3.

---

## 2. Reality check — Tại sao phải build custom

| Feature | Odoo 18.0 Community | Odoo Enterprise AI | OCA | Custom build |
|---|---|---|---|---|
| LLM chatbot | ❌ (im_livechat = rule-based) | ✅ (cloud, IAP credits) | ❌ | ✅ full control |
| RAG / Embedding | ❌ | ✅ (cloud) | ❌ | ✅ pgvector/Qdrant |
| AI Agent tool use | ❌ | ✅ (cloud) | ❌ | ✅ + HITL + audit |
| Self-hosted | ✅ | ❌ | ✅ | ✅ |
| Data privacy | ✅ | ❌ (cloud) | ✅ | ✅ |
| Cost | Free | IAP credits | Free | Hardware (Ollama) hoặc API (OpenAI) |

**Quyết định:** vì cần self-host + privacy + data ownership cho dự án này → custom build. Nếu sau này cần scale nhanh không có devops → mua Enterprise AI.

---

## 3. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (Odoo Web Client + OWL chat component)                 │
│      │                                                          │
│      ├─ bus.bus (longpolling :8072) — token-by-token streaming  │
│      └─ JSON-RPC → /chatbot/ask, /ai/search, /ai_agent/chat     │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│  Odoo 18.0 (odoo_app container)                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ai_chatbot controller                                      │ │
│  │   ├── /chatbot/ask      → LLM gateway (Ollama/OpenAI)      │ │
│  │   ├── discuss.channel writeback (mail.message)              │ │
│  │   └── bus.sendone('chatbot_<id>', {type, message_id})      │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ai_agent controller                                        │ │
│  │   ├── /ai_agent/chat    → agent loop + tool dispatcher     │ │
│  │   ├── /ai_agent/approve → HITL approval                    │ │
│  │   └── SSE/bus streaming tokens + tool results              │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ai_embedding model                                        │ │
│  │   ├── write() hook trên product.product, sale.order, ...   │ │
│  │   ├── queue_job async embed (OCA/server-tools/queue_job)   │ │
│  │   └── search_similar(query_vector) với ACL filter          │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────┬──────────────────────────────────────────────────────┘
           │ HTTP (internal docker network)
┌──────────▼──────────────────────────────────────────────────────┐
│  External services                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Ollama       │  │ OpenAI API   │  │ pgvector               │ │
│  │ llama3.2:3b  │  │ gpt-4o-mini  │  │ Postgres 16 (existing) │ │
│  │ nomic-embed  │  │ text-emb-3   │  │ hoặc Qdrant container  │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation phases (roadmap thực tế)

### Phase 0 — Prereq (½ ngày)

```bash
# Update odoo.conf addons_path
# Cần OCA queue_job (đã có OCA/server-tools trong entrypoint)
# Pull OCA queue_job vào addons/oca/server-tools/queue_job/

# .env additions:
POSTGRES_DB=odoo_dev
# Thêm config cho LLM provider (sau)
```

Không cần thêm container nào cho Phase 1-2 (dùng Ollama local, pgvector trong Postgres 16 đã có).

---

### Phase 1 — Chatbot cơ bản (1-2 tuần)

**Mục tiêu:** user chat được với LLM trong Odoo backend, response ghi vào `discuss.channel` + push qua `bus`.

**Module:** `addons/custom/ai_chatbot/`

```
ai_chatbot/
├── __manifest__.py            # depends: bus, im_livechat, mail
├── controllers/
│   └── chatbot_controller.py  # /chatbot/ask (JSON-RPC, auth='user')
├── models/
│   ├── chatbot_conversation.py  # lưu history, link discuss.channel
│   └── res_config_settings.py   # settings: provider, api_key, model
├── views/
│   └── chatbot_menus.xml        # menu "AI Assistant" + discuss embed
└── security/ir.model.access.csv
```

**Backend core (xem chatbot report §6.2):**
- `ChatbotAIController.ask(channel_id, message)` → call LLM → `channel.message_post(body=llm_response)` → `bus.sendone('chatbot_<id>', ...)`
- Provider abstracted: Ollama (default, free, dev) / OpenAI (production)
- Config lưu trong `ir.config_parameter` (không commit secrets)

**Frontend:** dùng OWL component nhúng vào discuss channel hoặc menu "AI Assistant" riêng.

**LLM choice (start):**
- Dev: `ollama pull llama3.2:3b` + `nomic-embed-text` (nếu Phase 2)
- Production: OpenAI `gpt-4o-mini` (~$0.15/1M tokens)

**Acceptance criteria:**
- [ ] User gõ message trong Odoo chat → LLM trả lời trong <5s
- [ ] Lịch sử conversation lưu lại được
- [ ] Bus notification update UI real-time
- [ ] Switch provider (Ollama ↔ OpenAI) qua Settings không cần restart

---

### Phase 2 — RAG (2-3 tuần)

**Mục tiêu:** chatbot tự retrieve context từ Odoo data (products, sale orders, knowledge articles...) trước khi gọi LLM.

**Module:** `addons/custom/ai_embedding/`

```
ai_embedding/
├── __manifest__.py            # depends: queue_job, mail
├── models/
│   ├── ai_embedding.py          # source_model, source_id, chunk_index, vector, content
│   ├── product_product.py       # _inherit: write() hook → queue_job
│   ├── sale_order.py            # _inherit
│   └── res_partner.py           # _inherit
├── controllers/
│   └── search_controller.py     # /ai/search (semantic search + ACL)
├── data/
│   └── ai_embedding_cron.xml    # cron re-embed dirty records
├── migrations/18.0.1.0/
│   └── post-migrate.py          # CREATE EXTENSION pgvector
└── security/ir.model.access.csv
```

**Critical decisions:**

1. **Vector store: pgvector (Postgres 16) cho dev, Qdrant cho production scale**
   - pgvector: 0 thêm container, đủ cho <100k chunks
   - Qdrant: ANN nhanh hơn, hybrid filter, cần thêm container
   - Khuyến nghị: start pgvector, migrate Qdrant khi >100k chunks

2. **Embedding model:**
   - Vietnamese + English: `BAAI/bge-m3` (Ollama: `nomic-embed-text` cho English-only)
   - Cheap cloud: OpenAI `text-embedding-3-small` (1536d, $0.02/1M tokens)
   - Self-host: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384d)

3. **Pipeline:**
   - `write()` hook → `queue_job.enqueue('ai_embedding.job', record_id)` (async, không block)
   - Cron hàng đêm re-embed dirty records
   - Chunking: 512 tokens, 64 overlap, tách theo line items + notes (xem RAG report §2.2)

4. **ACL — QUAN TRỌNG:** search method phải filter theo `env.user` permissions:
   ```python
   def _search_similar(self, query_vector, model=None, limit=5):
       # Get candidate embedding IDs from raw SQL
       candidates = self._raw_pgvector_search(query_vector, model, limit=limit*20)
       # Filter through Odoo ORM to enforce record rules
       return self.env[candidate_model].search([
           ('id', 'in', [c['res_id'] for c in candidates])
       ]).sudo().filtered(...)  # ở đây cần check kỹ
   ```
   User chỉ thấy chunks của records họ có quyền đọc.

5. **Multi-language:** dùng multilingual embedding model từ đầu. Đừng switch sau này (phải re-embed tất cả).

**Integration với Phase 1 chatbot:**
- Trước khi gọi LLM, chatbot controller gọi `/ai/search` để lấy top-K chunks
- Inject chunks vào system prompt:
  ```
  Context từ Odoo:
  - [product.product:42] Bút bi Thiên Long, code TL-001, giá 5000 VND
  - [sale.order:103] Đơn SO103 cho khách ABC, trạng thái draft

  User: đơn hàng của khách ABC đang ở trạng thái nào?
  ```

---

### Phase 3 — AI Agent (3-4 tuần, SAU khi RAG ổn định)

**Mục tiêu:** LLM tự gọi Odoo methods (search, create, write) qua tool-calling, có audit + HITL cho dangerous actions.

**Module:** `addons/custom/ai_agent/`

```
ai_agent/
├── __manifest__.py            # depends: ai_chatbot, bus, mail
├── tools/
│   ├── __init__.py
│   ├── dispatcher.py            # ToolDispatcher class, registry
│   ├── sale_tools.py            # search_sale_orders, create_sale_order
│   ├── product_tools.py         # search_products, get_product_info
│   ├── partner_tools.py         # search_partners
│   └── account_tools.py         # search_invoices (read-only, Phase 4)
├── controllers/
│   └── agent_controller.py      # /ai_agent/chat, /ai_agent/approve
├── models/
│   ├── ai_agent_conversation.py # history + tool_calls
│   ├── ai_agent_pending_approval.py  # HITL queue
│   └── res_users.py             # add 'AI Service User' group
├── views/
│   └── ai_agent_views.xml       # pending approvals tree/form
├── security/ir.model.access.csv
└── wizards/
    └── approve_action_wizard.py # approval dialog
```

**Critical design (xem agent report §4, §6, §8):**

1. **Tool schema = JSON Schema** (Anthropic / OpenAI / Ollama đều support)
   ```json
   {
     "name": "search_sale_orders",
     "description": "Tìm đơn hàng theo khách hoặc trạng thái",
     "parameters": {
       "type": "object",
       "properties": {
         "partner_name": {"type": "string"},
         "state": {"type": "enum": ["draft", "sale", "done", "cancel"]}
       }
     }
   }
   ```

2. **ToolDispatcher** — registry pattern:
   ```python
   class ToolDispatcher:
       _registry = {
           'search_sale_orders': self._search_sale_orders,
           'create_sale_order': self._create_sale_order,  # Phase 4
       }
       def dispatch(self, tool_call):
           fn = self._registry[tool_call['name']]
           return fn(**json.loads(tool_call['arguments']))
   ```

3. **Auth model — `sudo()` cẩn thận:**
   - Tạo `res.users` riêng: `AI Service User` (group `ai_agent.group_ai_service`)
   - Mọi tool execution chạy với `env(user=ai_service_user).sudo()`
   - **KHÔNG** dùng `superuser` — cần audit trail trong `mail.tracking.value`
   - Multi-company: enforce `company_id` check trong từng tool

4. **HITL (Human-in-the-loop) cho dangerous actions:**
   - **Read-only** (search, get_*): auto-execute
   - **Write low-risk** (create draft, add note): auto-execute + log
   - **Write high-risk** (confirm SO, post invoice, delete): → tạo `ai_agent.pending_approval`, notify qua bus, user approve/reject trong UI
   - Xem agent report §8 cho full list

5. **Streaming UX:**
   - Tool calls + tokens push qua `bus.bus.sendone(f'ai_agent_{channel_id}', ...)`
   - OWL component subscribe channel → render streaming
   - Pattern Anthropic/OpenAI SSE có thể dùng trực tiếp trong controller (xem agent report §11)

**Acceptance criteria:**
- [ ] User: "Tạo đơn hàng cho khách ABC, 5 cái bút bi" → agent search partner + product + create draft SO → confirm hay xin approval
- [ ] Mọi write operation có audit log (ai_agent.audit model hoặc `mail.tracking.value`)
- [ ] Dangerous action (confirm SO) tạo pending_approval → user click approve → SO confirmed
- [ ] Cost per conversation tracked + cảnh báo nếu >$1

---

### Phase 4 — Advanced (1-2 tháng sau)

- **Multi-agent:** orchestrator + specialists (sale, inventory, accounting) — dùng LangGraph
- **Workflow agent:** LLM route → predefined workflow (sequence of Odoo methods)
- **Voice input:** Whisper STT (xem langfens-speaking pattern) → text → chatbot
- **Proactive agent:** cron-driven ("khách X quá hạn 30 ngày → gửi reminder")
- **Fine-tuning:** collect user feedback (👍/👎 trên response) → fine-tune embedding reranker

---

## 5. Cost analysis (realistic)

**Setup cost (1 lần):**
- Dev: $0 (Ollama local, pgvector trong Postgres đã có)
- Prod: thêm Qdrant container (~$5-20/tháng VPS) hoặc Qdrant Cloud free tier

**Operating cost (per 1M tokens):**

| Provider | Model | Input | Output | Embedding |
|---|---|---|---|---|
| Ollama llama3.2:3b | local | $0 | $0 | $0 |
| Ollama llama3.2:8b | local | $0 | $0 | $0 |
| OpenAI gpt-4o-mini | cloud | $0.15 | $0.60 | — |
| OpenAI text-embedding-3-small | cloud | $0.02 | — | $0.02 |
| BGE-M3 (HF/Self-host) | local | $0 | $0 | $0 |

**Ước tính 1000 conversations/tháng (avg 500 tokens in + 300 out):**
- All-Ollama: $0 + điện
- Hybrid (Ollama dev + OpenAI prod): ~$0.50/tháng
- All-OpenAI: ~$0.30/tháng

→ **Recommendation:** start all-Ollama, switch OpenAI cho response quality quan trọng (agent, complex RAG).

---

## 6. Security & Governance

**Must-have từ ngày 1:**

1. **Secrets** — `ir.config_parameter` với `sudo()`, KHÔNG commit vào git. Thêm vào `.env` nếu dùng docker.
2. **ACL** — embedding search phải filter theo `env.user` (xem RAG report §8)
3. **Audit log** — mọi agent tool call ghi vào `ai_agent.audit` (model, args, user, company, result, timestamp)
4. **Rate limit** — controller có per-user limit (vd 60 req/hour) để chống cost blow-up
5. **Prompt injection defense** — system prompt KHÔNG trust user input. Inject retrieved context vào USER message, không phải system.
6. **PII redaction** — log không ghi raw user input, chỉ hash + length

**Multi-company:**
- Tool dispatcher enforce `company_id` filter
- Service user chỉ access company được assign
- Audit log có `company_id` field

---

## 7. Risks & open questions

| Risk | Mitigation |
|---|---|
| OCA queue_job chưa được cài local | Verify trong `addons/oca/server-tools/` trước Phase 2; nếu thiếu thì clone thêm |
| Ollama không có GPU trên server | Dùng `llama3.2:3b` chạy CPU OK trên 8GB RAM; hoặc fall back OpenAI |
| LLM hallucination tạo data sai | Agent: HITL approval cho write; Chatbot: cite source (chunk ID) trong response |
| Embedding model swap = re-embed tất cả | Chọn multilingual model từ đầu (BGE-M3) |
| Odoo Enterprise AI phát hành community fork | Theo dõi OCA + Odoo roadmap; migrate sang native nếu available |
| LLM API outage | Provider abstraction: 1 lệnh đổi Ollama ↔ OpenAI trong Settings |

---

## 8. Bước tiếp theo (action items)

1. **Verify OCA queue_job** đã có trong `addons/oca/server-tools/` chưa (entrypoint.sh đã clone, cần check submodule path)
2. **Test Ollama local** — `docker run -d -p 11434:11434 ollama/ollama`, pull `llama3.2:3b` + `nomic-embed-text`
3. **Scaffold `ai_chatbot`** module (copy từ `addons/custom/hello_shop`, modify __manifest__.py + add controller)
4. **Update odoo.conf addons_path** — thêm `addons/custom` (đã có sẵn theo config)
5. **Viết plan doc** cho Phase 1 trong `docs/superpowers/plans/ai-chatbot-phase1.md` (theo format `docs/superpowers/plans/`)
6. **Setup dev workflow** — branch `feature/ai-chatbot`, PR, test trên local trước khi deploy

---

## 9. References (tổng hợp từ 3 báo cáo)

**Odoo chính thức:**
- [Odoo 18.0 Documentation](https://www.odoo.com/documentation/18.0/)
- [Odoo 19.0 AI Features (Enterprise)](https://www.odoo.com/documentation/master/applications/ai/)
- [Odoo ai.agent (Enterprise)](https://www.odoo.com/documentation/18.0/developer/reference/ai/agent.html)
- [Odoo bus.bus](https://www.odoo.com/documentation/18.0/developer/reference/addons/bus.html)
- [Odoo im_livechat](https://www.odoo.com/documentation/18.0/applications/integrations/livechat.html)
- [Odoo mail.tracking.value](https://www.odoo.com/documentation/18.0/developer/reference/addons/mail.html)
- [OWL components](https://www.odoo.com/documentation/18.0/developer/reference/frontend/owl.html)

**OCA:**
- [OCA/server-tools 18.0](https://github.com/OCA/server-tools/tree/18.0)
- [queue_job OCA](https://github.com/OCA/server-tools/tree/18.0/queue_job)
- [OCA/server-ux 18.0](https://github.com/OCA/server-ux/tree/18.0)
- [OCA/website 18.0](https://github.com/OCA/website/tree/18.0)

**Vector / Embedding:**
- [pgvector Postgres 16](https://www.postgresql.org/docs/16/pgvector.html)
- [Qdrant](https://qdrant.tech/documentation/)
- [Chroma](https://docs.trychroma.com/)
- [Weaviate](https://weaviate.io/developers/weaviate)
- [Pinecone](https://docs.pinecone.io/)
- [BGE-M3 HuggingFace](https://huggingface.co/BAAI/bge-m3)
- [multilingual-e5](https://huggingface.co/intfloat/multilingual-e5)
- [OpenAI text-embedding-3-small](https://platform.openai.com/docs/guides/embeddings)
- [Ollama](https://github.com/ollama/ollama)
- [nomic-embed-text](https://ollama.com/library/nomic-embed-text)

**Agent frameworks:**
- [LangGraph](https://langchain.com/docs/langgraph)
- [PydanticAI](https://ai.pydantic.dev/)
- [Anthropic tool use](https://docs.anthropic.com/en/docs/build-claude-code/claude-code)
- [OpenAI Responses API](https://platform.openai.com/docs/guides/function-calling)
- [LlamaIndex](https://docs.llamaindex.ai/en/stable/)
- [FastAPI](https://fastapi.tiangolo.com/)
