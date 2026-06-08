# Phase 4 Proposal — Advanced AI Features

**Date:** 2026-06-08
**Duration:** 1-2 tháng
**Modules:** mở rộng `ai_chatbot`, `ai_embedding`, `ai_agent`
**Depends on:** Phase 1 + 2 + 3 production-stable (≥2 tháng traffic)
**Output:** Multi-agent specialization, multi-language, voice input, proactive agent, self-improvement

---

## 1. Goal

Sau khi core AI (chatbot + RAG + agent) chạy ổn định, mở rộng sang:
- **Multi-agent:** specialist agents cho từng domain (sale, inventory, accounting)
- **Multi-language UI:** trả lời đa ngôn ngữ (Anh/Việt/Nhật/Hàn/Trung)
- **Voice input:** Whisper STT → text → chatbot
- **Proactive agent:** cron-driven suggestions
- **Self-improvement:** feedback loop (👍/👎) → fine-tuning

---

## 2. Multi-agent orchestration (LangGraph)

### 2.1 Use case

User hỏi phức tạp: *"Khách Minh Tuấn có 3 đơn quá hạn thanh toán, kiểm tra tồn kho cho 2 sản phẩm trong đơn mới nhất, và gửi email nhắc nợ"*

→ Cần 3 agents phối hợp:
- **Sales Agent:** truy vấn sale.order
- **Inventory Agent:** truy vấn stock
- **Communication Agent:** soạn + gửi email (HITL approval)
- **Orchestrator:** route request, combine results

### 2.2 Module mới: `ai_agent_orchestrator`

```
addons/custom/ai_agent_orchestrator/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── orchestrator.py         # LangGraph orchestrator
│   └── specialist_agents.py    # sub-agents
├── services/
│   ├── __init__.py
│   └── langgraph_runtime.py    # LangGraph integration
├── views/
│   └── orchestrator_views.xml
└── security/
    └── ir.model.access.csv
```

### 2.3 Architecture

```
User Input
    ↓
[Orchestrator Agent] — routes to specialist(s)
    ├── [Sales Agent]      → search_sale_orders tool
    ├── [Inventory Agent]  → search_stock tool
    ├── [Accounting Agent] → search_invoices, post_payment
    └── [Communication Agent] → draft_email, send_email (HITL)
    ↓
[Orchestrator] — combine results, return final response
```

### 2.4 Implementation outline

```python
# addons/custom/ai_agent_orchestrator/services/langgraph_runtime.py
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    next_agent: str
    results: dict


def build_orchestrator_graph():
    workflow = StateGraph(AgentState)

    # Add specialist agents as nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("sales_agent", sales_agent_node)
    workflow.add_node("inventory_agent", inventory_agent_node)
    workflow.add_node("accounting_agent", accounting_agent_node)
    workflow.add_node("communication_agent", communication_agent_node)

    # Orchestrator decides routing
    workflow.add_conditional_edges(
        "orchestrator",
        route_decision,
        {
            "sales": "sales_agent",
            "inventory": "inventory_agent",
            "accounting": "accounting_agent",
            "communication": "communication_agent",
            "done": END,
        },
    )

    # All specialists return to orchestrator
    workflow.add_edge("sales_agent", "orchestrator")
    workflow.add_edge("inventory_agent", "orchestrator")
    workflow.add_edge("accounting_agent", "orchestrator")
    workflow.add_edge("communication_agent", "orchestrator")

    workflow.set_entry_point("orchestrator")
    return workflow.compile()
```

**Phase 4 partial scope:** ship 1 orchestrator + 2 specialists (sales + inventory) làm proof-of-concept. Mở rộng dần.

### 2.5 Effort: 8-12 ngày

---

## 3. Multi-language UI

### 3.1 Use case

Khách hàng Nhật chat bằng tiếng Nhật, agent trả lời tiếng Nhật, audit log ghi cả 2 version.

### 3.2 LLM provider

Cần MiniMax verify:
- Multi-language chat quality (Japanese, Korean, Chinese, English, Vietnamese)
- Embedding model multi-language tốt (cho Phase 2 RAG)

Nếu MiniMax yếu multi-language → fallback OpenAI/Anthropic cho non-Vietnamese.

### 3.3 Implementation outline

```python
# Detect user language → set system prompt
@api.model
def _detect_language(self, text):
    # Use langdetect or LLM for first 2 sentences
    from langdetect import detect
    try:
        return detect(text)
    except:
        return 'en'

@api.model
def _build_multilang_system_prompt(self, lang):
    base = self.env['ir.config_parameter'].sudo().get_param('ai_chatbot.system_prompt')
    lang_instruction = {
        'vi': 'Trả lời bằng tiếng Việt.',
        'en': 'Reply in English.',
        'ja': '日本語で返信してください。',
        'ko': '한국어로 답변해 주세요.',
        'zh': '请用中文回答。',
    }
    return f"{base}\n\n{lang_instruction.get(lang, lang_instruction['en'])}"
```

### 3.4 Effort: 3-5 ngày (mostly testing translation quality)

---

## 4. Voice input (Whisper STT)

### 4.1 Use case

User nói vào micro → Whisper transcribe → text → chatbot xử lý như message thường.

### 4.2 Architecture

```
Browser MediaRecorder → WebM/Opus audio blob
    ↓ POST /ai_voice/transcribe
[Odoo controller]
    ↓
[Whisper service] — local (faster-whisper) hoặc OpenAI Whisper API
    ↓
[Transcribed text] → /chatbot/ask (Phase 1)
```

### 4.3 Module mới: `ai_voice`

```
addons/custom/ai_voice/
├── __init__.py
├── __manifest__.py
├── controllers/
│   └── voice_controller.py     # /ai_voice/transcribe
├── models/
│   └── voice_transcript.py     # log transcripts
├── services/
│   └── whisper_client.py       # Whisper API client
├── static/
│   └── src/
│       ├── voice_recorder.js   # MediaRecorder component
│       └── voice_recorder.xml
└── security/ir.model.access.csv
```

### 4.4 Code outline

```python
# addons/custom/ai_voice/services/whisper_client.py
import requests


class WhisperClient:
    def __init__(self, api_key, base_url='https://api.openai.com/v1', model='whisper-1'):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def transcribe(self, audio_bytes, language=None):
        files = {'file': ('audio.webm', audio_bytes, 'audio/webm')}
        data = {'model': self.model}
        if language:
            data['language'] = language
        resp = requests.post(
            f'{self.base_url}/audio/transcriptions',
            headers={'Authorization': f'Bearer {self.api_key}'},
            files=files, data=data, timeout=60,
        )
        resp.raise_for_status()
        return resp.json()['text']
```

**MiniMax option:** verify nếu MiniMax có speech-to-text API → dùng. Nếu không → OpenAI Whisper (~$0.006/min audio).

### 4.5 Frontend

```js
// MediaRecorder API → blob → upload
class VoiceRecorder extends Component {
    async startRecording() {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.recorder = new MediaRecorder(this.stream);
        this.chunks = [];
        this.recorder.ondataavailable = (e) => this.chunks.push(e.data);
        this.recorder.start();
    }

    async stopRecording() {
        return new Promise((resolve) => {
            this.recorder.onstop = async () => {
                const blob = new Blob(this.chunks, { type: 'audio/webm' });
                const text = await this.upload(blob);
                resolve(text);
            };
            this.recorder.stop();
        });
    }
}
```

### 4.6 Effort: 5-7 ngày

---

## 5. Proactive agent (cron-driven)

### 5.1 Use case

Hàng ngày / hàng tuần, agent tự chạy và đề xuất hành động:
- *"Khách ABC thanh toán trễ 30 ngày, tổng 50M. Gửi email nhắc?"*
- *"Sản phẩm X tồn kho dưới ngưỡng 10, đặt hàng nhà cung cấp?"*
- *"Có 5 lead mới từ web chưa ai liên hệ >24h"*

### 5.2 Module mới: `ai_proactive`

```
addons/custom/ai_proactive/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── proactive_rule.py        # rule definition (cron schedule + prompt + action)
│   └── proactive_run.py         # execution log
├── jobs/
│   └── proactive_job.py         # queue_job worker
├── data/
│   └── default_rules.xml        # sample rules
├── views/
│   ├── proactive_rule_views.xml
│   └── proactive_run_views.xml
└── security/ir.model.access.csv
```

### 5.3 Rule example

```xml
<record id="rule_overdue_invoices" model="ai.proactive.rule">
    <field name="name">Overdue invoices check</field>
    <field name="model_id" ref="account.model_account_move"/>
    <field name="domain">[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('invoice_date_due', '&lt;', (context_today() - timedelta(days=30)).isoformat()), ('amount_residual', '&gt;', 0)]</field>
    <field name="cron_interval">1</field>
    <field name="cron_interval_type">days</field>
    <field name="prompt">
        Tìm các khách hàng có hóa đơn quá hạn >30 ngày. 
        Tóm tắt theo từng khách (số đơn, tổng tiền). 
        Đề xuất email nhắc nợ cho từng khách (subject + body).
    </field>
    <field name="notification_channel">email</field>
    <field name="notification_user_ids" eval="[(4, ref('base.user_admin'))]"/>
</record>
```

### 5.4 Execution flow

```
[Cron] → [queue_job worker] → [Fetch records matching rule]
    ↓
[LLM: analyze + suggest actions]
    ↓
[Notification to user with suggested actions]
    ↓
[User click "Approve" → execute suggested actions]
```

### 5.5 Effort: 6-8 ngày

---

## 6. Self-improvement (feedback loop)

### 6.1 Use case

Mỗi AI response có 👍/👎. Negative feedback lưu lại để:
- Reranker train lại (cho Phase 2 RAG)
- Tool selection improve (cho Phase 3 agent)
- Few-shot examples update (inject good examples vào prompt)

### 6.2 Module mới: `ai_feedback`

```
addons/custom/ai_feedback/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── ai_feedback.py            # thumbs up/down + comment
│   └── ai_few_shot.py            # curated good examples
├── data/
│   └── default_few_shot.xml
├── views/
│   └── ai_feedback_views.xml
└── security/ir.model.access.csv
```

### 6.3 Model

```python
class AIFeedback(models.Model):
    _name = 'ai.feedback'
    
    conversation_id = fields.Many2one('ai.agent.conversation', required=True)
    message_id = fields.Many2one('mail.message', required=True)
    rating = fields.Selection([('up', '👍'), ('down', '👎')], required=True)
    comment = fields.Text()
    user_id = fields.Many2one('res.users', required=True)
    
    # LLM context
    prompt_snapshot = fields.Text(help='Prompt đã dùng khi tạo response này')
    response_snapshot = fields.Text(help='Response đã generate')
    tool_calls_snapshot = fields.Text(help='Tool calls đã thực hiện')
    retrieved_chunks_snapshot = fields.Text(help='RAG chunks đã dùng')
```

### 6.4 OWL UI

```xml
<!-- Thêm vào agent chat message -->
<div class="o_ai_message_feedback">
    <button t-on-click="() => this.feedback('up')" 
            t-attf-class="fa fa-thumbs-up {{ state.feedback === 'up' ? 'active' : '' }}"/>
    <button t-on-click="() => this.feedback('down')" 
            t-attf-class="fa fa-thumbs-down {{ state.feedback === 'down' ? 'active' : '' }}"/>
    <button t-if="state.feedback" t-on-click="() => this.openComment()">
        <i class="fa fa-comment"/>
    </button>
</div>
```

### 6.5 Use of feedback

- **Daily report:** email manager với negative feedback count
- **Few-shot examples:** manually mark 👍 responses as gold examples → inject vào system prompt
- **Prompt iteration:** A/B test với few-shot examples mới
- **Fine-tuning (Phase 5+):** export feedback dataset → fine-tune embedding reranker

### 6.6 Effort: 4-6 ngày

---

## 7. Semantic chunking + reranking (Phase 2 enhancement)

### 7.1 Current limitation (Phase 2)

Naive chunker split by sentence → có thể break semantic context.

### 7.2 Upgrade

```python
# Use LangChain SemanticChunker
from langchain_experimental.text_splitter import SemanticChunker
from langchain.embeddings.base import Embeddings


class OdooEmbeddingsAdapter(Embeddings):
    """Wrap our embedding client as LangChain Embeddings interface."""
    def __init__(self, client):
        self.client = client

    def embed_documents(self, texts):
        return self.client.embed(texts)

    def embed_query(self, text):
        return self.client.embed([text])[0]


def chunk_semantic(text, client):
    splitter = SemanticChunker(
        OdooEmbeddingsAdapter(client),
        breakpoint_threshold_type='percentile',
    )
    return splitter.split_text(text)
```

### 7.3 Reranker (optional, for higher accuracy)

Use cross-encoder model to rerank top-K chunks:

```python
# Use BGE-reranker-v2-m3
from sentence_transformers import CrossEncoder

reranker = CrossEncoder('BAAI/bge-reranker-v2-m3')

def rerank(query, chunks, top_k=5):
    pairs = [(query, c['chunk_text']) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [c for c, s in ranked[:top_k]]
```

**Trade-off:** reranker add ~100-200ms latency + extra model. Optional cho high-value queries.

### 7.4 Effort: 3-5 ngày

---

## 8. Embedding ảnh/PDF (advanced content)

### 8.1 Use case

`ir.attachment` có PDF, DOCX, ảnh → extract text → embed.

### 8.2 Tools needed

- **PDF:** `pypdf`, `pdfplumber`, hoặc `unstructured`
- **DOCX:** `python-docx`
- **Ảnh:** OCR (Tesseract) hoặc multimodal LLM (GPT-4V, Claude vision)
- **Audio:** Whisper (xem §4)

### 8.3 Module mới: `ai_attachment_extract`

```
addons/custom/ai_attachment_extract/
├── __init__.py
├── __manifest__.py
├── models/
│   └── ir_attachment.py        # _inherit: extract on upload
├── services/
│   ├── pdf_extractor.py
│   ├── docx_extractor.py
│   └── ocr_client.py
└── security/ir.model.access.csv
```

### 8.4 Effort: 5-7 ngày

---

## 9. Embedding ảnh/PDF — CLIP/Visual (advanced)

*(Bao gồm trong §8)*

---

## 10. Memory + personalization

### 10.1 Use case

AI nhớ preferences của từng user:
- *"Tôi thích format response bullet points"*
- Agent lưu lại, dùng cho session sau.

### 10.2 Implementation

```python
class AIUserMemory(models.Model):
    _name = 'ai.user.memory'
    
    user_id = fields.Many2one('res.users', required=True, index=True)
    key = fields.Char(required=True, help='e.g. "response_format"')
    value = fields.Text(required=True)
    confidence = fields.Float(default=1.0)
    last_used = fields.Datetime()
```

Khi build system prompt:
```python
memories = self.env['ai.user.memory'].search([('user_id', '=', user.id)])
preferences = "\n".join(f"- {m.key}: {m.value}" for m in memories)
system_prompt = f"{base_prompt}\n\nUser preferences:\n{preferences}"
```

### 10.3 Effort: 3-4 ngày

---

## 11. Cost dashboard (admin)

### 11.1 Use case

Admin xem dashboard: chi phí AI theo provider, user, model, theo ngày/tuần/tháng.

### 11.2 Module mới: `ai_dashboard`

```
addons/custom/ai_dashboard/
├── controllers/
│   └── dashboard_controller.py
├── views/
│   └── dashboard_views.xml
└── static/
    └── src/
        ├── dashboard.js
        └── dashboard.xml
```

### 11.3 Effort: 4-6 ngày

---

## 12. Production hardening (security & ops)

### 12.1 Rate limiting per user

```python
# Add to all controllers
@http.route(...)
def my_route(self, ...):
    user = request.env.user
    recent_count = self.env['ai.agent.audit'].search_count([
        ('create_uid', '=', user.id),
        ('create_date', '>=', fields.Datetime.subtract(fields.Datetime.now(), hours=1)),
    ])
    if recent_count > 60:  # 60 req/hour
        raise UserError(_('Rate limit exceeded. Try again in an hour.'))
    ...
```

### 12.2 PII redaction trong logs

```python
def redact_pii(text):
    import re
    # Email
    text = re.sub(r'[\w.-]+@[\w.-]+', '[EMAIL]', text)
    # Phone VN
    text = re.sub(r'0\d{9,10}', '[PHONE]', text)
    return text
```

### 12.3 Metrics export (Prometheus)

```python
# Expose /metrics endpoint
from prometheus_client import Counter, Histogram, generate_latest

AI_REQUESTS = Counter('ai_requests_total', 'Total AI requests', ['provider', 'model'])
AI_LATENCY = Histogram('ai_latency_seconds', 'AI response latency', ['provider'])

class MetricsController(http.Controller):
    @http.route('/metrics', type='http', auth='public')
    def metrics(self):
        return generate_latest()
```

### 12.4 Effort: 4-6 ngày

---

## 13. Phased rollout (recommended)

| Sub-phase | Duration | Scope |
|---|---|---|
| **4a: Foundation** | 2 tuần | Multi-language UI + voice input + memory |
| **4b: Proactive** | 2 tuần | Proactive rules + cron + email notification |
| **4c: Quality** | 2 tuần | Semantic chunking + reranker + feedback loop |
| **4d: Scale** | 2-3 tuần | Multi-agent orchestrator + cost dashboard + content extraction |
| **4e: Hardening** | 1 tuần | Rate limit + PII redaction + Prometheus metrics |

**Total: ~10 tuần (2.5 tháng)** nếu làm full.

User có thể chọn sub-phases ưu tiên tùy use case:
- E-commerce focus → 4a (multi-language) + 4c (quality)
- Internal ops focus → 4b (proactive) + 4d (multi-agent)
- Cost-sensitive → 4e (hardening) trước

---

## 14. Acceptance criteria (per sub-phase)

### 4a
- [ ] User chat tiếng Nhật → response tiếng Nhật
- [ ] Voice input: speak Vietnamese → transcribed → chatbot respond
- [ ] User memory: "tôi thích bullet points" → subsequent responses use bullets

### 4b
- [ ] Cron "Overdue invoices" runs daily → email admin với suggested actions
- [ ] User click "Approve" từ email → agent executes (soạn + gửi email nhắc nợ)

### 4c
- [ ] Semantic chunking produces better chunks (manual eval trên 10 records)
- [ ] 👍/👎 buttons on every AI message
- [ ] Few-shot examples injected vào system prompt (configurable)

### 4d
- [ ] Orchestrator routes "đơn + kho + email" → 3 specialists phối hợp
- [ ] Cost dashboard: bar chart chi phí theo provider/user/day
- [ ] PDF/DOCX upload → content extracted → embedded

### 4e
- [ ] Rate limit: user gọi >60 req/hour → 429 error
- [ ] PII in audit log → redacted
- [ ] Prometheus scrape `/metrics` → counters work

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| LangGraph complexity | Start với 1 orchestrator + 2 specialists; scale dần |
| Whisper API cost (nếu dùng OpenAI) | Cache transcripts; hoặc self-host faster-whisper |
| Multi-language quality kém | A/B test providers; user-configurable default |
| Proactive rules spam user | Configurable frequency; user opt-in per rule |
| Feedback loop vô tình train trên bad examples | Manager review trước khi mark few-shot |
| Reranker latency thêm 200ms | Optional qua settings; cache rerank results |
| Multi-agent vòng lặp vô tận | Hard cap iterations; orchestrator timeout |

---

## 16. Deliverables (full Phase 4)

1. `ai_agent_orchestrator/` — LangGraph orchestrator + 4 specialists
2. `ai_voice/` — Whisper STT integration
3. `ai_proactive/` — Cron-driven rules + notifications
4. `ai_feedback/` — 👍/👎 + few-shot examples
5. `ai_attachment_extract/` — PDF/DOCX/OCR
6. `ai_dashboard/` — Cost dashboard
7. Enhanced `ai_embedding/` — semantic chunking + reranker
8. Memory model in `ai_chatbot/`
9. Rate limiting + PII redaction + Prometheus metrics
10. Documentation + runbook

---

## 17. Effort estimate (full Phase 4)

| Sub-phase | Days |
|---|---|
| 4a: Foundation | 12-15 |
| 4b: Proactive | 12-15 |
| 4c: Quality | 10-12 |
| 4d: Scale | 15-20 |
| 4e: Hardening | 6-8 |
| **Total** | **55-70 ngày (10-13 tuần, ~3 tháng)** |

---

## 18. Phase 5+ (future, beyond this proposal)

- **Fine-tuning embedding model** on Odoo-specific data (using feedback dataset)
- **Fine-tuning LLM** (LoRA) on Odoo domain conversations
- **Custom dashboard widgets** (charts, KPIs)
- **Mobile app** (Odoo Mobile + voice-first)
- **External integrations** (Zalo, Messenger, WhatsApp as input channels)
- **Agentic workflows** (visual workflow builder, n8n-style)

---

## 19. Decision points for user

Trước khi bắt đầu Phase 4, confirm với user:

1. **MiniMax capabilities (verify):**
   - Multi-language chat quality (Japanese, Korean, Chinese)?
   - Speech-to-text API available?
   - Tool use spec stable?

2. **Sub-phase priority:** 4a → 4e, hay chọn lọc?

3. **Self-hosting vs cloud:**
   - Whisper: OpenAI API ($0.006/min) vs local faster-whisper (free, +CPU)
   - Reranker: cross-encoder local (free) vs Cohere API (fast, $$)
   - OCR: Tesseract local (free) vs cloud (better quality)

4. **Feedback dataset size:** nếu <1000 examples → không đủ fine-tune; nếu >10k → cân nhắc Phase 5.

---

**Liên hệ để thảo luận ưu tiên Phase 4 + verify MiniMax API specs còn thiếu.**
