# Phase 1 Proposal — AI Chatbot cơ bản

**Date:** 2026-06-08
**Duration:** 1-2 tuần
**Module mới:** `addons/custom/ai_chatbot/`
**Depends on:** `bus`, `im_livechat`, `mail` (built-in Odoo)
**Output:** Chatbot LLM hoạt động trong Odoo backend, ghi vào `discuss.channel`, real-time qua `bus.bus`

---

## 1. Goal

User chat với LLM ngay trong Odoo, response ghi vào `discuss.channel` + push qua `bus.bus` cho real-time UI. Provider-agnostic (Ollama local hoặc MiniMax/OpenAI cloud, switch qua Settings).

---

## 2. LLM Provider — MiniMax

**Cấu hình dự kiến:**

| Biến | Giá trị | Lưu trong |
|---|---|---|
| `AI_PROVIDER` | `minimax` (default) / `ollama` / `openai` | `ir.config_parameter` |
| `MINIMAX_API_KEY` | (user cung cấp) | `.env` → `ir.config_parameter` |
| `MINIMAX_BASE_URL` | `https://api.minimax.chat/v1` (verify) | `.env` |
| `MINIMAX_MODEL` | (verify model ID) | Settings |
| `MINIMAX_TIMEOUT` | 30s | Settings |

**Caveat cần verify với user:**
- MiniMax API endpoint + auth scheme (OpenAI-compatible?)
- Model names available (chat model + embedding model nếu Phase 2)
- Rate limits + pricing
- Streaming support (SSE?)

> **Tôi không có thông tin về MiniMax API trong training data.** Phase 1 này build với abstraction layer (giống OpenAI client), nên khi có docs MiniMax thật chỉ cần thay 1 wrapper class.

**Abstraction design:**

```python
# addons/custom/ai_chatbot/services/llm_client.py
class LLMClient:
    """Abstract base — tất cả provider kế thừa interface này."""
    def chat(self, messages: list[dict], **kwargs) -> str: ...
    def stream_chat(self, messages: list[dict], **kwargs) -> Iterator[str]: ...

class MinimaxClient(LLMClient):
    """MiniMax-specific. Cần verify API spec trước khi impl."""
    def __init__(self, api_key, base_url, model): ...

class OllamaClient(LLMClient):
    """Local fallback. Dùng khi MiniMax down hoặc dev offline."""
    def __init__(self, base_url='http://localhost:11434', model='llama3.2:3b'): ...

class OpenAIClient(LLMClient):
    """Backup cloud provider."""
    ...
```

Provider chọn qua `ir.config_parameter` — không cần restart, không cần code change.

---

## 3. Module structure

```
addons/custom/ai_chatbot/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── chatbot_controller.py     # /chatbot/ask (JSON-RPC, auth='user')
├── models/
│   ├── __init__.py
│   ├── chatbot_conversation.py   # lưu conversation history
│   ├── res_config_settings.py    # settings UI
│   └── discuss_channel.py        # _inherit: thêm field ai_assistant_enabled
├── services/
│   ├── __init__.py
│   ├── llm_client.py             # base + 3 implementations
│   └── prompt_builder.py         # system prompt template
├── views/
│   ├── chatbot_menus.xml         # menu "AI Assistant"
│   ├── chatbot_conversation_views.xml
│   └── res_config_settings_views.xml
├── security/
│   ├── ir.model.access.csv
│   └── security.xml              # res.groups: ai_chatbot.group_user, ai_chatbot.group_manager
├── data/
│   └── default_config.xml        # default system prompt, model params
└── static/
    └── src/
        ├── components/
        │   ├── ai_chat_panel/    # OWL component
        │   │   ├── ai_chat_panel.js
        │   │   ├── ai_chat_panel.xml
        │   │   └── ai_chat_panel.scss
        │   └── ai_message/
        │       ├── ai_message.js
        │       └── ai_message.xml
        └── bus_service.js         # bus subscription helper
```

---

## 4. __manifest__.py

```python
{
    'name': 'AI Chatbot',
    'version': '18.0.1.0.0',
    'summary': 'LLM-powered chatbot integrated with Odoo discuss',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'category': 'Productivity/AI',
    'depends': ['bus', 'im_livechat', 'mail', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/default_config.xml',
        'views/chatbot_menus.xml',
        'views/chatbot_conversation_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_chatbot/static/src/bus_service.js',
            'ai_chatbot/static/src/components/ai_chat_panel/*',
            'ai_chatbot/static/src/components/ai_message/*',
        ],
    },
    'installable': True,
    'auto_install': False,
}
```

---

## 5. Backend — Controller

**Route:** `POST /chatbot/ask` (JSON-RPC, `auth='user'`)

```python
# addons/custom/ai_chatbot/controllers/chatbot_controller.py
import json
import logging
import requests
from odoo import http, _
from odoo.http import request
from odoo.addons.bus.models.bus import Bus

_logger = logging.getLogger(__name__)


class ChatbotAIController(http.Controller):

    @http.route('/chatbot/ask', type='json', auth='user', csrf=False)
    def ask(self, channel_id, message, **kwargs):
        """User gửi message → LLM trả lời → ghi vào discuss.channel → push bus."""
        channel = request.env['discuss.channel'].browse(channel_id)
        if not channel.exists():
            return {'error': _('Channel not found')}
        if not channel.sudo().ai_assistant_enabled:
            return {'error': _('AI assistant not enabled in this channel')}

        # 1. Persist user message
        user_msg = channel.message_post(
            body=message,
            message_type='comment',
            author_id=request.env.user.partner_id.id,
            subtype_xmlid='mail.mt_comment',
        )

        # 2. Build conversation context (last N messages)
        history = channel._get_chat_history(limit=20)
        messages = history + [{'role': 'user', 'content': message}]

        # 3. Call LLM
        try:
            client = request.env['chatbot.conversation']._get_llm_client()
            llm_response = client.chat(messages)
        except Exception as e:
            _logger.exception("LLM call failed")
            return {'error': _('AI service unavailable: %s') % str(e)}

        # 4. Persist assistant message
        ai_msg = channel.message_post(
            body=llm_response,
            message_type='comment',
            author_id=channel.sudo()._get_ai_partner_id(),
            subtype_xmlid='mail.mt_comment',
        )

        # 5. Save conversation history
        request.env['chatbot.conversation'].sudo().create({
            'channel_id': channel.id,
            'user_message_id': user_msg.id,
            'ai_message_id': ai_msg.id,
            'user_id': request.env.user.id,
            'llm_provider': request.env['ir.config_parameter'].sudo().get_param(
                'ai_chatbot.provider', 'minimax'
            ),
        })

        # 6. Push bus notification
        Bus().sendone(
            f'chatbot_channel_{channel.id}',
            {
                'type': 'new_message',
                'message_id': ai_msg.id,
                'channel_id': channel.id,
            },
        )

        return {
            'message': llm_response,
            'message_id': ai_msg.id,
        }
```

---

## 6. Backend — LLM Client abstraction

```python
# addons/custom/ai_chatbot/services/llm_client.py
import logging
import time
import requests
from abc import ABC, abstractmethod

_logger = logging.getLogger(__name__)


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages, **kwargs) -> str: ...
    @abstractmethod
    def stream_chat(self, messages, **kwargs): ...


class MinimaxClient(LLMClient):
    """MiniMax API client.
    
    NOTE: API spec chưa verify. Dự kiến OpenAI-compatible.
    Khi có docs thật, update base_url + headers + payload shape.
    """
    def __init__(self, api_key, base_url, model, timeout=30):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def chat(self, messages, **kwargs):
        # TODO: verify exact endpoint + payload với MiniMax docs
        resp = requests.post(
            f'{self.base_url}/chat/completions',
            headers=self._headers(),
            json={'model': self.model, 'messages': messages, **kwargs},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']

    def stream_chat(self, messages, **kwargs):
        # TODO: implement khi cần streaming
        raise NotImplementedError("Streaming chưa impl cho Phase 1")


class OllamaClient(LLMClient):
    """Local Ollama — fallback khi MiniMax down hoặc dev offline."""
    def __init__(self, base_url='http://localhost:11434', model='llama3.2:3b', timeout=30):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

    def chat(self, messages, **kwargs):
        resp = requests.post(
            f'{self.base_url}/api/chat',
            json={'model': self.model, 'messages': messages, 'stream': False},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()['message']['content']

    def stream_chat(self, messages, **kwargs):
        resp = requests.post(
            f'{self.base_url}/api/chat',
            json={'model': self.model, 'messages': messages, 'stream': True},
            timeout=self.timeout,
            stream=True,
        )
        for line in resp.iter_lines():
            if line:
                chunk = line.decode('utf-8')
                if chunk.startswith('data: '):
                    data = json.loads(chunk[6:])
                    if 'message' in data and 'content' in data['message']:
                        yield data['message']['content']


class OpenAIClient(LLMClient):
    """OpenAI backup — same shape as MiniMax (assumed OpenAI-compatible)."""
    def __init__(self, api_key, model='gpt-4o-mini', timeout=30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = 'https://api.openai.com/v1'

    def chat(self, messages, **kwargs):
        resp = requests.post(
            f'{self.base_url}/chat/completions',
            headers={'Authorization': f'Bearer {self.api_key}'},
            json={'model': self.model, 'messages': messages, **kwargs},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
```

---

## 7. Backend — Models

```python
# addons/custom/ai_chatbot/models/chatbot_conversation.py
import json
from odoo import api, fields, models, _


class ChatbotConversation(models.Model):
    _name = 'chatbot.conversation'
    _description = 'AI Chatbot Conversation Log'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    channel_id = fields.Many2one('discuss.channel', required=True, index=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True)
    user_message_id = fields.Many2one('mail.message')
    ai_message_id = fields.Many2one('mail.message')
    llm_provider = fields.Selection([
        ('minimax', 'MiniMax'),
        ('ollama', 'Ollama (local)'),
        ('openai', 'OpenAI'),
    ], required=True)
    llm_model = fields.Char()
    prompt_tokens = fields.Integer()
    completion_tokens = fields.Integer()
    cost_usd = fields.Float(digits=(10, 6))
    latency_ms = fields.Integer()
    error = fields.Text()

    display_name = fields.Char(compute='_compute_display_name')

    @api.depends('create_date', 'user_id')
    def _compute_display_name(self):
        for r in self:
            r.display_name = f"{r.user_id.name} - {fields.Datetime.to_string(r.create_date)}"

    def _get_llm_client(self):
        """Factory — return active LLM client based on config."""
        ICP = self.env['ir.config_parameter'].sudo()
        provider = ICP.get_param('ai_chatbot.provider', 'minimax')

        if provider == 'minimax':
            return MinimaxClient(
                api_key=ICP.get_param('ai_chatbot.minimax_api_key', ''),
                base_url=ICP.get_param('ai_chatbot.minimax_base_url', 'https://api.minimax.chat/v1'),
                model=ICP.get_param('ai_chatbot.minimax_model', ''),
            )
        elif provider == 'ollama':
            return OllamaClient(
                base_url=ICP.get_param('ai_chatbot.ollama_url', 'http://ollama:11434'),
                model=ICP.get_param('ai_chatbot.ollama_model', 'llama3.2:3b'),
            )
        elif provider == 'openai':
            return OpenAIClient(
                api_key=ICP.get_param('ai_chatbot.openai_api_key', ''),
                model=ICP.get_param('ai_chatbot.openai_model', 'gpt-4o-mini'),
            )
        raise ValueError(f"Unknown provider: {provider}")


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    ai_assistant_enabled = fields.Boolean(
        string='AI Assistant Enabled',
        default=True,
        help='Allow AI chatbot to respond in this channel',
    )
    chatbot_conversation_ids = fields.One2many(
        'chatbot.conversation', 'channel_id',
        string='AI Conversations',
    )

    def _get_chat_history(self, limit=20):
        """Build message list for LLM context (last N messages)."""
        messages = self.env['mail.message'].search_read(
            [('res_id', '=', self.id), ('model', '=', 'discuss.channel'),
             ('message_type', '=', 'comment')],
            ['body', 'author_id'],
            order='create_date desc', limit=limit,
        )
        # Reverse chronological → oldest first
        result = []
        for m in reversed(messages):
            role = 'assistant' if m['author_id'][0] == self.sudo()._get_ai_partner_id() else 'user'
            result.append({'role': role, 'content': m['body']})
        return result

    def _get_ai_partner_id(self):
        """AI bot partner — auto-create nếu chưa có."""
        partner = self.env['res.partner'].search([('name', '=', 'AI Assistant')], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({'name': 'AI Assistant', 'is_company': False})
        return partner.id
```

---

## 8. Settings UI

```xml
<!-- addons/custom/ai_chatbot/views/res_config_settings_views.xml -->
<record id="res_config_settings_view_form_ai_chatbot" model="ir.ui.view">
    <field name="name">res.config.settings.view.form.ai.chatbot</field>
    <field name="model">res.config.settings</field>
    <field name="inherit_id" ref="base.res_config_settings_view_form"/>
    <field name="arch" type="xml">
        <div id="ai_chatbot" position="inside">
            <block string="AI Chatbot" name="ai_chatbot_settings">
                <setting string="LLM Provider" id="ai_chatbot_provider">
                    <field name="ai_chatbot_provider" class="o_light_label" widget="selection"/>
                </setting>
                <!-- MiniMax -->
                <setting string="MiniMax API Key" invisible="ai_chatbot_provider != 'minimax'">
                    <field name="ai_chatbot_minimax_api_key" password="True"/>
                </setting>
                <setting string="MiniMax Base URL" invisible="ai_chatbot_provider != 'minimax'">
                    <field name="ai_chatbot_minimax_base_url"/>
                </setting>
                <setting string="MiniMax Model" invisible="ai_chatbot_provider != 'minimax'">
                    <field name="ai_chatbot_minimax_model"/>
                </setting>
                <!-- Ollama -->
                <setting string="Ollama URL" invisible="ai_chatbot_provider != 'ollama'">
                    <field name="ai_chatbot_ollama_url"/>
                </setting>
                <setting string="Ollama Model" invisible="ai_chatbot_provider != 'ollama'">
                    <field name="ai_chatbot_ollama_model"/>
                </setting>
                <!-- OpenAI -->
                <setting string="OpenAI API Key" invisible="ai_chatbot_provider != 'openai'">
                    <field name="ai_chatbot_openai_api_key" password="True"/>
                </setting>
                <setting string="OpenAI Model" invisible="ai_chatbot_provider != 'openai'">
                    <field name="ai_chatbot_openai_model"/>
                </setting>
            </block>
        </div>
    </field>
</record>
```

```python
# addons/custom/ai_chatbot/models/res_config_settings.py
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_chatbot_provider = fields.Selection([
        ('minimax', 'MiniMax'),
        ('ollama', 'Ollama (local)'),
        ('openai', 'OpenAI'),
    ], string='AI Chatbot Provider', config_parameter='ai_chatbot.provider', default='minimax')

    ai_chatbot_minimax_api_key = fields.Char(
        config_parameter='ai_chatbot.minimax_api_key',
    )
    ai_chatbot_minimax_base_url = fields.Char(
        config_parameter='ai_chatbot.minimax_base_url',
        default='https://api.minimax.chat/v1',
    )
    ai_chatbot_minimax_model = fields.Char(
        config_parameter='ai_chatbot.minimax_model',
    )

    ai_chatbot_ollama_url = fields.Char(
        config_parameter='ai_chatbot.ollama_url',
        default='http://ollama:11434',
    )
    ai_chatbot_ollama_model = fields.Char(
        config_parameter='ai_chatbot.ollama_model',
        default='llama3.2:3b',
    )

    ai_chatbot_openai_api_key = fields.Char(
        config_parameter='ai_chatbot.openai_api_key',
    )
    ai_chatbot_openai_model = fields.Char(
        config_parameter='ai_chatbot.openai_model',
        default='gpt-4o-mini',
    )
```

---

## 9. Frontend — OWL Chat Panel

**Mount point:** Discuss channel sidebar HOẶC standalone menu "AI Assistant"

```js
/** @odoo-module **/
// addons/custom/ai_chatbot/static/src/components/ai_chat_panel/ai_chat_panel.js

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ChatBubble } from "../ai_message/ai_message";


export class AIChatPanel extends Component {
    static template = "ai_chatpanel.AIChatPanel";
    static components = { ChatBubble };
    static props = {
        channelId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.busService = useService("bus_service");
        this.notification = useService("notification");

        this.state = useState({
            messages: [],
            input: "",
            loading: false,
        });

        onMounted(() => this._subscribeBus());
        onWillUnmount(() => this._unsubscribeBus());
    }

    async _subscribeBus() {
        this.busSubscription = this.busService.subscribe(
            `chatbot_channel_${this.props.channelId}`,
            (payload) => this._onBusMessage(payload),
        );
    }

    _unsubscribeBus() {
        if (this.busSubscription) {
            this.busService.unsubscribe(this.busSubscription);
        }
    }

    _onBusMessage(payload) {
        if (payload.type === 'new_message') {
            this._refreshMessages();
        }
    }

    async _refreshMessages() {
        // Read last 50 messages from channel
        const messages = await this.orm.call(
            "discuss.channel",
            "get_ai_chat_history",
            [this.props.channelId, 50],
        );
        this.state.messages = messages;
    }

    async sendMessage() {
        const text = this.state.input.trim();
        if (!text || this.state.loading) return;

        this.state.loading = true;
        this.state.input = "";

        // Optimistic UI: show user message immediately
        this.state.messages.push({ role: "user", body: text, id: `tmp_${Date.now()}` });

        try {
            const result = await this.orm.call(
                "chatbot.conversation",
                "ask",
                [this.props.channelId, text],
            );
            if (result.error) {
                this.notification.add(result.error, { type: "danger" });
            }
            await this._refreshMessages();
        } catch (e) {
            this.notification.add(_t("Failed to send message"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="ai_chatpanel.AIChatPanel">
        <div class="o_ai_chat_panel">
            <div class="o_ai_chat_panel_header">
                <h4>AI Assistant</h4>
                <span t-if="state.loading" class="o_ai_chat_loading">Thinking...</span>
            </div>
            <div class="o_ai_chat_messages">
                <t t-foreach="state.messages" t-as="msg" t-key="msg.id">
                    <ChatBubble message="msg"/>
                </t>
            </div>
            <div class="o_ai_chat_input">
                <textarea
                    t-model="state.input"
                    t-on-keydown="(ev) => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); this.sendMessage(); } }"
                    placeholder="Hỏi AI gì đó..."
                    rows="2"/>
                <button t-on-click="sendMessage" t-att-disabled="state.loading || !state.input.trim()">
                    Send
                </button>
            </div>
        </div>
    </t>
</templates>
```

---

## 10. Security

```csv
<!-- addons/custom/ai_chatbot/security/ir.model.access.csv -->
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_chatbot_conversation_user,chatbot.conversation.user,model_chatbot_conversation,base.group_user,1,0,0,0
access_chatbot_conversation_manager,chatbot.conversation.manager,model_chatbot_conversation,ai_chatbot.group_chatbot_manager,1,1,1,1
```

```xml
<!-- addons/custom/ai_chatbot/security/security.xml -->
<odoo>
<data noupdate="1">
    <record id="module_category_ai_chatbot" model="ir.module.category">
        <field name="name">AI Chatbot</field>
    </record>

    <record id="group_chatbot_user" model="res.groups">
        <field name="name">AI Chatbot / User</field>
        <field name="category_id" ref="module_category_ai_chatbot"/>
        <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
    </record>

    <record id="group_chatbot_manager" model="res.groups">
        <field name="name">AI Chatbot / Manager</field>
        <field name="category_id" ref="module_category_ai_chatbot"/>
        <field name="implied_ids" eval="[(4, ref('group_chatbot_user'))]"/>
        <field name="users" eval="[(4, ref('base.user_admin'))]"/>
    </record>
</data>
</odoo>
```

---

## 11. Deployment steps

### 11.1 Local dev

```bash
# 1. Tạo module skeleton (copy từ addons/custom/hello_shop)
cp -r addons/custom/hello_shop addons/custom/ai_chatbot
# Sửa __manifest__.py (xem §4)

# 2. Add MiniMax API key vào .env
cat >> .env <<EOF
# AI Chatbot
AI_CHATBOT_PROVIDER=minimax
AI_CHATBOT_MINIMAX_API_KEY=your-key-here
AI_CHATBOT_MINIMAX_BASE_URL=https://api.minimax.chat/v1
AI_CHATBOT_MINIMAX_MODEL=minimax-text-01
EOF

# 3. Odoo.conf không cần đổi (addons/custom đã có trong addons_path)

# 4. Restart Odoo, install module
./scripts/cli.sh -d odoo_dev -i ai_chatbot --stop-after-init
docker compose restart odoo

# 5. Test:
# - Vào Settings → AI Chatbot → set provider + key
# - Mở Discuss → channel mới → bật AI Assistant
# - Gõ "Hello" → check response
```

### 11.2 Production

```bash
# Tương tự local, dùng production .env + docker-compose.prod.yml
# Thêm rate limit (vd 60 req/user/hour) trước khi go-live
# Setup monitoring: log lỗi LLM, latency, cost
```

---

## 12. Acceptance criteria

- [ ] Module install không lỗi
- [ ] Settings page hiển thị 3 providers, switch OK
- [ ] MiniMax API call thành công (cần user verify API spec)
- [ ] User gõ message trong discuss channel → AI trả lời trong <5s
- [ ] Message lưu vào `mail.message` với author = AI Assistant partner
- [ ] Conversation history load lại khi refresh page
- [ ] Bus notification update UI không cần reload
- [ ] Fallback Ollama hoạt động khi MiniMax down
- [ ] ACL: user không có `ai_chatbot.group_chatbot_user` không thấy menu AI

---

## 13. Out of scope (defer sang Phase 2+)

- ❌ RAG (tìm context từ Odoo data) → Phase 2
- ❌ Streaming response (token-by-token) → Phase 2 hoặc 3
- ❌ Tool use (gọi Odoo methods) → Phase 3
- ❌ Human-in-the-loop approval → Phase 3
- ❌ Multi-language UI → Phase 4
- ❌ Voice input → Phase 4

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| MiniMax API spec chưa biết | Abstraction layer; verify trước khi implement; fallback Ollama |
| Rate limit MiniMax | Per-user rate limit (60 req/hour) trong controller |
| Prompt injection | System prompt cứng (không nhận user-controlled content vào system role) |
| Cost blow-up | Log `cost_usd` mỗi conversation; admin alert nếu daily >$X |
| LLM API key lộ | Lưu `ir.config_parameter` với `password=True`; KHÔNG commit vào git |

---

## 15. Deliverables

1. Module `addons/custom/ai_chatbot/` — installable, tested local
2. Settings UI cho 3 providers
3. OWL chat panel component
4. Conversation history logging
5. Bus real-time update
6. Basic rate limit (60 req/user/hour)
7. `.env.example` updated với MiniMax config
8. README.md trong module — install + usage

---

## 16. Effort estimate

- Backend: 3-4 ngày (controller, model, LLM client, settings)
- Frontend: 2-3 ngày (OWL component, bus integration)
- Testing + bugfix: 2-3 ngày
- Docs: 1 ngày
- **Total: 8-11 ngày làm việc (1.5-2 tuần)**

---

## 17. Next phase

Sau khi Phase 1 ổn định (~2 tuần production traffic) → chuyển sang [Phase 2: RAG](./proposal-phase2-rag.md)
