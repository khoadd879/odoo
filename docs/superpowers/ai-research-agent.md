# AI Agent cho Odoo 18.0 — Nghiên cứu

**Date:** 2026-06-08
**Focus:** AI Agent (tool-using, autonomous action) trong Odoo 18.0 Community Edition

---

## 1. Tổng quan

```
Odoo 18.0 Community
├── ai.agent              ← Enterprise-only, cloud lock-in
├── bus.bus               ← real-time notification channel
├── discuss.channel       ← conversation model
├── im_livechat           ← rule-based chatbot (NO LLM, NO tool use)
└── Không có native AI Agent cho Community
```

**Verdict:** Odoo 18.0 Community không có native AI Agent. Muốn AI Agent phải build custom. Odoo Enterprise AI (`ai.agent`) không self-hosted được, yêu cầu Odoo Online/Enterprise + IAP credits.

---

## 2. Odoo 18/19 Native — `ai.agent`

| Feature | Community | Enterprise AI |
|---|---|---|
| AI Agent | No | Yes |
| Self-hosted | Yes | No |
| Tool use | No | Yes (built-in) |
| Cost | Free | IAP credits |

**Kết luận:** Muốn AI Agent self-hosted phải build custom.

---

## 3. Agent Design Patterns

### Pattern (A) — Tool-using Agent
```
User Input → LLM (with tool schema) → Tool: search_sale_order() → ORM call → Odoo model
```
- LLM generate tool calls từ JSON Schema
- Backend execute tool, return result
- LLM synthesize final response

### Pattern (B) — Workflow Agent
```
User Input → LLM Router → Workflow: create_so_workflow
  ├── Step 1: search_partner("X")
  ├── Step 2: create_sale_order()
  └── Step 3: confirm_sale_order()
```
- LLM routing input sang predefined workflow
- Workflow = sequence of deterministic steps

### Pattern (C) — Multi-agent
```
User Input → Orchestrator Agent
  ├── Sub-agent: Order Agent (sale orders)
  ├── Sub-agent: Inventory Agent (stock)
  └── Sub-agent: Customer Agent (partner)
```
- Mỗi sub-agent specialized cho một domain
- Orchestrator route request sang sub-agent phù hợp

---

## 4. Tool / Function Calling Shape

### JSON Schema for Odoo Tools

```json
{
  "name": "search_sale_orders",
  "description": "Search sale orders by partner or status",
  "parameters": {
    "type": "object",
    "properties": {
      "partner_id": {"type": "integer", "description": "res.partner id"},
      "state": {"type": "string", "enum": ["draft", "sale", "done", "cancel"]},
      "limit": {"type": "integer", "default": 10}
    },
    "required": ["partner_id"]
  }
}
```

### Tool Dispatcher Pattern

```python
# addons/custom/ai_agent/tools/dispatcher.py
import json, logging
_logger = logging.getLogger(__name__)

class ToolDispatcher:
    def __init__(self, env):
        self.env = env
        self._registry = {
            'search_sale_orders': self._search_sale_orders,
            'create_sale_order': self._create_sale_order,
            'get_product_info': self._get_product_info,
            'search_stock_picking': self._search_stock_picking,
            'create_stock_picking': self._create_stock_picking,
            'get_partner_info': self._get_partner_info,
        }

    def dispatch(self, tool_call):
        name = tool_call.get('name')
        arguments = tool_call.get('arguments', {})
        if name not in self._registry:
            return {'error': f'Unknown tool: {name}'}
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            return self._registry[name](**arguments)
        except Exception as e:
            _logger.error("Tool dispatch error for %s: %s", name, e)
            return {'error': str(e)}

    def _search_sale_orders(self, partner_id, state=None, limit=10):
        domain = [('partner_id', '=', partner_id)]
        if state:
            domain.append(('state', '=', state))
        orders = self.env['sale.order'].sudo().search(
            domain, limit=limit, order='date_order desc')
        return {'orders': [{'id': o.id, 'name': o.name, 'state': o.state,
                             'amount_total': o.amount_total} for o in orders]}

    def _create_sale_order(self, partner_id, line_ids):
        partner = self.env['res.partner'].sudo().browse(partner_id)
        if not partner.exists():
            return {'error': f'Partner {partner_id} not found'}
        so_vals = {'partner_id': partner_id, 'order_line': [
            (0, 0, {'product_id': l['product_id'],
 'product_uom_qty': l['product_uom_qty']}) for l in line_ids]}
        so = self.env['sale.order'].sudo().create(so_vals)
        return {'id': so.id, 'name': so.name, 'state': so.state}
```

---

## 5. Frameworks

### LangGraph
Graph-based agent framework cho complex workflows.
```python
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

@tool
def search_sale_orders(partner_id: int) -> dict:
    orders = env['sale.order'].sudo().search([('partner_id', '=', partner_id)])
    return {'orders': [{'id': o.id, 'name': o.name} for o in orders]}

tools = [search_sale_orders]
tool_node = ToolNode(tools)
model = ChatOpenAI(model="gpt-4o")
```
**Pros:** Production-grade, LangSmith observability. **Cons:** Heavy, complex setup.

### PydanticAI
Lightweight agent framework với Pydantic output validation.
```python
from pydantic_ai import Agent, tool

@tool
def search_sale_orders(partner_id: int) -> str:
    orders = env['sale.order'].sudo().search([('partner_id', '=', partner_id)])
    return json.dumps([{'id': o.id, 'name': o.name} for o in orders])

agent = Agent('openai:gpt-4o-mini', tools=[search_sale_orders])
```
**Pros:** Pydantic-first, type-safe. **Cons:** Newer project.

### Claude Tool Use (Anthropic)
```python
import anthropic
client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514", max_tokens=1024,
    tools=[{"name": "search_sale_orders", "description": "Search sale orders",
            "input_schema": {"type": "object", "properties": {
                "partner_id": {"type": "integer"}, "state": {"type": "string"}}}}],
    messages=[{"role": "user", "content": "Find draft orders for partner 5"}]
)
for tool_use in response.content:
    if tool_use.type == "tool_use":
        result = dispatcher.dispatch(tool_use)
```
**Pros:** Strong reasoning. **Cons:** Cloud-only, per-token cost.

### OpenAI Responses API
```python
from openai import OpenAI
client = OpenAI()
response = client.responses.create(
    model="gpt-4o",
    input="Create a sale order for partner5 with product1, qty 2",
    tools=[{"type": "function", "name": "create_sale_order",
            "description": "Create sale order in Odoo",
            "parameters": {"type": "object", "properties": {
                "partner_id": {"type": "integer"}, "line_ids": {"type": "array"}},
 "required": ["partner_id", "line_ids"]}}]
)
```
**Pros:** Native function calling. **Cons:** Cloud-only.

### LlamaIndex
RAG-focused agents.
```python
from llama_index.core.agent import FunctionCallingAgent
from llama_index.core.tools import FunctionTool

def search_sale_orders(partner_id: int) -> dict:
    orders = env['sale.order'].sudo().search([('partner_id', '=', partner_id)])
    return [{'id': o.id, 'name': o.name} for o in orders]

tool = FunctionTool.from_defaults(search_sale_orders)
agent = FunctionCallingAgent.from_tools([tool], llm=llm)
```
**Pros:** Excellent RAG integration. **Cons:** RAG-focused.

### Comparison Table

| Framework | Tool Use | Workflow | Multi-agent | Learning Curve |
|---|---|---|---|---|
| **LangGraph** | Yes | Yes (graph) | Yes | High |
| **PydanticAI** | Yes | Yes (simple) | Limited | Low |
| **Claude** | Yes | Via prompt | Manual | Medium |
| **OpenAI Responses** | Yes | Via prompt | Manual | Low |
| **LlamaIndex** | Yes | Yes | Limited | Medium |

**Recommendation:** Simple agents: PydanticAI / OpenAI Responses. Complex workflows: LangGraph. RAG-focused: LlamaIndex + LangGraph.

---

## 6. Auth / Audit

### `sudo()` Caveats
```python
# DANGER: sudo() bypasses ALL access rights
orders = self.env['sale.order'].sudo().search([])  # ALL orders!

# BETTER: sudo with specific user context
orders = self.env['sale.order'].sudo(user_id).search([])

# BEST: Use service user with minimal required access
service_user = self.env.ref('base.user_admin')
orders = self.env['sale.order'].sudo(service_user.id).search([])
```

### Multi-company Security
```python
# Automatic company filtering via Odoo ORM
orders = self.env['sale.order'].search([
    ('partner_id', '=', partner_id),
    ('company_id', 'in', self.env.companies.ids),  # Auto-filtered
])

# Explicit check
def create_sale_order(self, partner_id, line_ids):
    partner = self.env['res.partner'].browse(partner_id)
    if partner.company_id and partner.company_id != self.env.company:
        raise AccessError("Cannot create order for different company")
```

### `mail.tracking.value` for Audit
```python
# Odoo auto-tracks field changes when mail.thread is inherited
class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'mail.thread']
    # All field changes auto-tracked via mail.tracking_value

# Query audit log
tracking_values = self.env['mail.tracking.value'].search([
    ('mail_message_id.res_id', '=', record.id)
], order='write_date desc')
```

### Service User Pattern
```xml
<!-- In data/demo.xml -->
<record id="ai_agent_service_user" model="res.users">
    <field name="name">AI Agent Service</field>
    <field name="login">ai_agent_service</field>
    <field name="company_id" ref="base.main_company"/>
</record>
```

---

## 7. Bus / Streaming UX

### `bus.bus` — Odoo Real-time Channel
```python
from odoo.addons.bus.models.bus import Bus
Bus().sendone('chatbot_channel_1', {
    'type': 'new_message', 'message_id': 42, 'body': 'AI response text',
})
```

### SSE (Server-Sent Events)
```python
@http.route('/chatbot/stream', type='http', auth='public')
def stream(self, channel_id):
    def generate():
        yield "data: ping\n\n"
        for token in llm_stream_generator():
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    return response
```

### OWL Chat Component
```javascript
class StreamingChat extends Component {
    setup() {
        useService("bus").subscribe('ai_token', (data) => {
            this.pendingMessage += data.token;
        });
    }
}
```

### Architecture Flow
```
Frontend (OWL Chat)
  └── fetch('/ai_agent/ask', {stream: true})
        ▼
Controller: /ai_agent/ask
  └── spawn background thread
        ▼
Agent Loop: LLM → tool_calls → ToolDispatcher → ORM
 └── bus.sendone('ai_token', {token: '...'})
        ▼
Frontend receives via useBus()
```

---

## 8. Human-in-the-Loop

### Approval Model
```python
class PendingApproval(models.Model):
    _name = 'ai_agent.pending_approval'

    name = fields.Char()
    tool_calls = fields.Serialized()
    state = fields.Selection([('pending', 'Pending'), ('approved', 'Approved'),
                              ('rejected', 'Rejected')], default='pending')
    requested_by = fields.Many2one('res.users', default=lambda self: self.env.user)
    approved_by = fields.Many2one('res.users')

    def approve(self):
        dispatcher = ToolDispatcher(self.env)
        for tool_call in self.tool_calls:
            dispatcher.dispatch(tool_call)
        self.write({'state': 'approved', 'approved_by': self.env.user.id})

    def reject(self):
        self.write({'state': 'rejected'})
```

### Dangerous Action List
```python
DANGEROUS_ACTIONS = [
    'create_sale_order', 'cancel_sale_order', 'create_stock_picking',
    'write_account_move', 'delete_res_partner', 'write_ir_config_param',
]

def dispatch_with_approval(self, tool_call):
    if tool_call['name'] in DANGEROUS_ACTIONS:
        approval = self.env['ai_agent.pending_approval'].create({
            'name': f"Approve {tool_call['name']}", 'tool_calls': [tool_call],
            'state': 'pending',
        })
        Bus().sendone('ai_agent_approvers', {'type': 'pending_approval',
                                              'approval_id': approval.id})
        return {'status': 'pending_approval', 'approval_id': approval.id}
    return self.dispatch(tool_call)
```

---

## 9. Use Cases per OCA Module

| Module | Tools | Example |
|---|---|---|
| **Sale** | search_sale_orders, create_sale_order, confirm_sale_order | "Create SO for Acme with 10x product A" |
| **Account** | search_account_moves, create_payment, get_invoice_pdf | "Show unpaid invoices from last month" |
| **Stock** | get_stock_quant, create_stock_picking, validate_stock_picking | "Transfer 50 units from WH/Stock to WH/Output" |
| **Website** | search_products, create_website_lead | "Find products matching 'laptop'" |
| **Server Tools** | execute_sql (admin), import_csv, export_records | "Export all sale orders to CSV" |

---

## 10. Cost / Safety / Governance

### Cost Ceiling
```python
COST_LIMITS = {'per_user_per_day': 5.00}  # USD
def check_cost_ceiling(self, user_id, provider='openai'):
    today = fields.Date.today()
    spending = self.env['ai_agent.cost_log'].search([
        ('user_id', '=', user_id), ('date', '=', today), ('provider', '=', provider)])
    if sum(spending.mapped('cost')) >= COST_LIMITS['per_user_per_day']:
        raise ValueError("Cost ceiling reached")
```

### Prompt Injection Defense
```python
INJECTION_PATTERNS = [r'ignore\s+(previous|all)\s+(instructions|commands)',
    r'(system|prompt)\s*:\s*[^.]', r'illegal|hack|exploit']
def sanitize_user_input(self, text):
    import re
    text = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "[Input sanitized]"
    return text[:4000] if len(text) > 4000 else text
```

### Log Redaction (PII patterns)
```python
PII_PATTERNS = [(r'\b\d{9}\b', '[SSN]'),
 (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
    (r'\b\+?[\d\s\-\(\)]{10,}\b', '[PHONE]')]
def _sanitize_for_log(self, text):
    import re
    for pattern, replacement in PII_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
```

---

## 11. OWL + Python Skeleton

### Module Structure
```
addons/custom/ai_agent/
├── __init__.py, __manifest__.py
├── controllers/ai_agent_controller.py
├── models/ai_agent_conversation.py, ai_agent_pending_approval.py
├── tools/dispatcher.py, sale_tools.py, stock_tools.py
├── components/ai_chat_window/ai_chat_window.js
└── security/ir.model.access.csv
```

### OWL Chat Component
```javascript
/** @odoo-module **/
import { Component, useState, useBus } from "@odoo/owl";
import { jsonrpc } from "@web/core/network/rpc_service";

export class AiChatWindow extends Component {
    static template = "ai_agent.AiChatWindow";
    setup() {
        this.state = useState({ messages: [], inputValue: "", streaming: false });
        useBus(this.env.bus, "ai_agent.token", (ev) => this.addToken(ev.detail.token));
    }
    async sendMessage() {
        if (!this.state.inputValue.trim()) return;
        this.state.messages.push({ role: "user", content: this.state.inputValue });
        this.state.inputValue = "";
        this.state.streaming = true;
        try {
            await jsonrpc("/ai_agent/ask", {
                channel_id: this.props.channelId, message: this.state.inputValue, stream: true,
            });
        } catch (error) {
            this.state.messages.push({ role: "assistant", content: "Error: " + error.message });
        } finally { this.state.streaming = false; }
    }
    addToken(token) {
        const last = this.state.messages[this.state.messages.length - 1];
        if (last && last.role === "assistant" && last.pending) last.content += token;
        else this.state.messages.push({ role: "assistant", content: token, pending: true });
    }
}
```

### Python Controller (key parts)
```python
# addons/custom/ai_agent/controllers/ai_agent_controller.py
import json, logging
from odoo import http
from odoo.http import request
from odoo.addons.bus.models.bus import Bus
_logger = logging.getLogger(__name__)

class AiAgentController(http.Controller):

    @http.route('/ai_agent/ask', type='json', auth='user', csrf=False)
    def ask(self, channel_id, message, stream=True, **kwargs):
        channel = request.env['discuss.channel'].browse(channel_id)
        if not channel.exists(): return {'error': 'Channel not found'}
        sanitized = self._sanitize(message)
        conversation = self._get_or_create_conversation(channel_id)
        return self._run_agent_loop(sanitized, conversation, stream)

    def _sanitize(self, text):
        import re
        text = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
        return text[:4000] if len(text) > 4000 else text

    def _get_or_create_conversation(self, channel_id):
        Conv = request.env['ai_agent.conversation']
        conversation = Conv.search([('channel_id', '=', channel_id)], limit=1)
        if not conversation:
            conversation = Conv.create({'channel_id': channel_id})
        return conversation

    def _run_agent_loop(self, message, conversation, stream=True):
        from addons.custom.ai_agent.tools.dispatcher import ToolDispatcher
        dispatcher = ToolDispatcher(request.env)
        provider = request.env['ir.config_parameter'].sudo().get_param('ai_agent.provider', 'openai')
        messages = [{"role": "system", "content": "You are an Odoo AI assistant."}]
        history = json.loads(conversation.message_history or '[]')
        for msg in history[-10:]: messages.append({"role": msg['role'], "content": msg['content']})
        messages.append({"role": "user", "content": message})
        tool_schema = self._get_tool_schema()
        messages[0]['content'] = f"You are an AI assistant for Odoo ERP. Available tools:\n{json.dumps(tool_schema)}\n\nUser: {message}"
        if provider == 'openai': return self._call_openai_stream(messages, conversation, stream, dispatcher)
        elif provider == 'ollama': return self._call_ollama(messages, conversation)
        return {'error': 'Unknown provider'}

    def _get_tool_schema(self):
        return [{"type": "function", "function": {
            "name": "search_sale_orders", "description": "Search sale orders by partner",
            "parameters": {"type": "object", "properties": {
                "partner_id": {"type": "integer"}, "state": {"type": "string"}, "limit": {"type": "integer", "default": 10}},
                "required": ["partner_id"]}}},
            {"type": "function", "function": {
                "name": "create_sale_order", "description": "Create a sale order",
                "parameters": {"type": "object", "properties": {
                    "partner_id": {"type": "integer"}, "line_ids": {"type": "array"}},
 "required": ["partner_id", "line_ids"]}}}]

    def _call_openai_stream(self, messages, conversation, stream, dispatcher):
        import openai
        api_key = request.env['ir.config_parameter'].sudo().get_param('ai_agent.openai_api_key', '')
        if not api_key: return {'error': 'OpenAI API key not configured'}
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(model='gpt-4o-mini', messages=messages,
            tools=self._get_tool_schema(), stream=stream)
        if stream:
            def generate():
                full = ""
                for chunk in response:
                    if chunk.choices[0].delta.tool_calls:
                        tc = chunk.choices[0].delta.tool_calls[0]
                        result = dispatcher.dispatch({'name': tc.function.name, 'arguments': tc.function.arguments})
                        messages.append({"role": "assistant", "content": "", "tool_calls": [
                            {"id": tc.id, "type": "function", "function": {"name": tc.function.name,
 "arguments": tc.function.arguments}}]})
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
                        yield f"data: {json.dumps({'type': 'tool_result', 'result': result})}\n\n"
                    elif chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full += token
                        Bus().sendone(f'ai_agent_{conversation.channel_id.id}', {'type': 'token', 'token': token})
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                conversation.add_message('user', messages[-1]['content'])
                conversation.add_message('assistant', full)
            return Response(generate(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache'})
        return response

    def _call_ollama(self, messages, conversation):
        import requests
        ollama_url = request.env['ir.config_parameter'].sudo().get_param('ai_agent.ollama_url', 'http://localhost:11434')
        model = request.env['ir.config_parameter'].sudo().get_param('ai_agent.ollama_model', 'llama3.2:3b')
        try:
            resp = requests.post(f"{ollama_url}/api/chat", json={'model': model, 'messages': messages, 'stream': False}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            content = data['message']['content']
            conversation.add_message('user', messages[-1]['content'])
            conversation.add_message('assistant', content)
            return {'response': content}
        except Exception as e:
            _logger.error("Ollama call failed: %s", e)
            return {'error': str(e)}

    @http.route('/ai_agent/approve', type='json', auth='user', csrf=False)
    def approve(self, approval_id, **kwargs):
        approval = request.env['ai_agent.pending_approval'].browse(approval_id)
        if not approval.exists() or approval.state != 'pending': return {'error': 'Approval not found'}
        from addons.custom.ai_agent.tools.dispatcher import ToolDispatcher
        dispatcher = ToolDispatcher(request.env)
        results = [dispatcher.dispatch(tc) for tc in approval.tool_calls]
        approval.write({'state': 'approved', 'approved_by': request.env.user.id})
        return {'results': results}

    @http.route('/ai_agent/reject', type='json', auth='user', csrf=False)
    def reject(self, approval_id, **kwargs):
        approval = request.env['ai_agent.pending_approval'].browse(approval_id)
        if not approval.exists(): return {'error': 'Approval not found'}
        approval.write({'state': 'rejected'})
        return {'status': 'rejected'}
```

### Conversation Model
```python
class AiAgentConversation(models.Model):
    _name = 'ai_agent.conversation'
    channel_id = fields.Many2one('discuss.channel', required=True, index=True)
    message_history = fields.Text(default='[]')
    user_id = fields.Many2one('res.users')
    create_date = fields.Datetime(default=fields.Datetime.now)

    def add_message(self, role, content):
        history = json.loads(self.message_history or '[]')
        history.append({'role': role, 'content': content, 'timestamp': fields.Datetime.now().isoformat()})
        if len(history) > 50: history = history[-50:]
        self.message_history = json.dumps(history)
```

---

## 12. Recommended Path

| Phase | Time | Tasks | Tools |
|---|---|---|---|
| **1: Foundation** | Week 1-2 | Module skeleton, ToolDispatcher (3-5 read-only tools), Controller + streaming, OWL chat + bus | search_sale_orders, get_product_info, get_partner_info |
| **2: Security** | Week 3 | Input sanitization, audit logging + PII redaction, cost tracking, service user + multi-company | — |
| **3: HITL** | Week 4 | PendingApproval model, approval dialog OWL, dangerous action detection + bus notification | — |
| **4: Advanced** | Week 5-6 | Write tools (create_sale_order, create_stock_picking), account tools, multi-agent + LangGraph | — |

### LLM Provider

| Stage | Provider | Model | Cost |
|---|---|---|---|
| Dev/Test | Ollama | llama3.2:3b | Free |
| Production (budget) | Ollama | llama3.2:8b | Hardware only |
| Production (quality) | OpenAI | gpt-4o-mini | ~$0.15/1M tokens |

**Start with Ollama for dev, migrate to OpenAI for production if budget allows.**

---

## 13. References

1. [Odoo ai.agent (Enterprise)](https://www.odoo.com/documentation/18.0/developer/reference/ai/agent.html)
2. [Odoo bus.bus — Real-time notifications](https://www.odoo.com/documentation/18.0/developer/reference/addons/bus.html)
3. [Odoo im_livechat — Chatbot architecture](https://www.odoo.com/documentation/18.0/applications/integrations/livechat.html)
4. [LangGraph — Multi-agent orchestration](https://langchain.com/docs/langgraph)
5. [PydanticAI — Lightweight agent framework](https://ai.pydantic.dev/)
6. [Anthropic Claude — Tool use](https://docs.anthropic.com/en/docs/build-claude-code/claude-code)
7. [OpenAI Responses API — Function calling](https://platform.openai.com/docs/guides/function-calling)
8. [LlamaIndex — RAG-focused agents](https://docs.llamaindex.ai/en/stable/)
9. [Odoo mail.tracking.value — Audit trail](https://www.odoo.com/documentation/18.0/developer/reference/addons/mail.html)
10. [OWL — Odoo Web Library components](https://www.odoo.com/documentation/18.0/developer/reference/frontend/owl.html)
11. [Odoo sudo() — Security best practices](https://www.odoo.com/documentation/18.0/developer/reference/addons/security.html)
12. [PostgreSQL LISTEN/NOTIFY — Odoo bus backend](https://www.postgresql.org/docs/current/sql-notify.html)
