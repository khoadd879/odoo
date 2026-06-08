# Phase 3 Proposal — AI Agent (Tool Use + HITL)

**Date:** 2026-06-08
**Duration:** 3-4 tuần
**Module mới:** `addons/custom/ai_agent/`
**Depends on:** `ai_chatbot` (Phase 1), `ai_embedding` (Phase 2), `mail`, `bus`
**Output:** LLM tự gọi Odoo methods (search/create/write) qua tool-calling, có audit log + Human-in-the-Loop approval cho dangerous actions

---

## 1. Goal

Chatbot không chỉ trả lời, mà tự động thực hiện thao tác trong Odoo:
- Read-only (search, get): auto-execute
- Low-risk write (create draft, add note): auto-execute + log
- High-risk write (confirm SO, post invoice, delete): tạo pending approval → user approve/reject

Mọi thao tác đều ghi log (audit) + push bus notification.

---

## 2. LLM Provider — MiniMax (tool use)

**Cần verify với user:**
- MiniMax hỗ trợ tool use / function calling? (Anthropic/OpenAI-style?)
- API spec cho tool calls (parameters JSON Schema? hay custom format?)
- Streaming + tool calls combined?

**Abstraction (mở rộng từ Phase 1):**

```python
# addons/custom/ai_agent/services/llm_client_agent.py
class LLMAgentClient(LLMClient):
    """LLM client with tool-calling support."""
    
    @abstractmethod
    def chat_with_tools(self, messages, tools, **kwargs) -> 'LLMResponse':
        """LLM returns text + tool calls."""
        ...


class MinimaxAgentClient(LLMAgentClient):
    """MiniMax client with tool use.
    
    TODO: verify tool calling spec. Có thể OpenAI-compatible:
      response.choices[0].message.tool_calls = [
        {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
      ]
    """
    def chat_with_tools(self, messages, tools, **kwargs):
        resp = requests.post(
            f'{self.base_url}/chat/completions',
            headers=self._headers(),
            json={
                'model': self.model,
                'messages': messages,
                'tools': tools,  # JSON Schema list
                'tool_choice': kwargs.get('tool_choice', 'auto'),
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data['choices'][0]['message']
        return LLMResponse(
            content=msg.get('content', ''),
            tool_calls=msg.get('tool_calls', []),
            usage=data.get('usage', {}),
        )


@dataclass
class LLMResponse:
    content: str
    tool_calls: list  # list of {"id", "name", "arguments"}
    usage: dict  # {prompt_tokens, completion_tokens, total_tokens}
```

**Fallback:** nếu MiniMax không hỗ trợ tool use → dùng LangGraph + OpenAI/Ollama (có tool use chắc chắn) trong khi MiniMax phát triển.

---

## 3. Module structure

```
addons/custom/ai_agent/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   ├── agent_controller.py     # /ai_agent/chat, /approve, /reject
│   └── streaming_controller.py  # SSE endpoint for token streaming
├── models/
│   ├── __init__.py
│   ├── ai_agent_conversation.py  # conversation + tool_calls history
│   ├── ai_agent_pending_approval.py  # HITL approval queue
│   ├── ai_agent_audit.py        # audit log
│   ├── res_users.py             # 'AI Service User' group + user
│   ├── res_config_settings.py   # agent config
│   └── discuss_channel.py       # _inherit: enable agent mode
├── services/
│   ├── __init__.py
│   ├── llm_client_agent.py      # LLM with tool use
│   └── tool_dispatcher.py       # tool registry + executor
├── tools/
│   ├── __init__.py
│   ├── base.py                  # BaseTool ABC
│   ├── sale_tools.py            # search_sale_orders, create_sale_order
│   ├── product_tools.py         # search_products, get_product_info
│   ├── partner_tools.py         # search_partners, create_partner
│   ├── account_tools.py         # search_invoices (read-only)
│   └── stock_tools.py           # search_stock, create_picking
├── views/
│   ├── ai_agent_pending_approval_views.xml
│   ├── ai_agent_audit_views.xml
│   ├── ai_agent_conversation_views.xml
│   ├── approve_wizard_views.xml
│   └── res_config_settings_views.xml
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
├── wizards/
│   ├── __init__.py
│   └── approve_action_wizard.py  # Odoo wizard for approval UI
├── data/
│   └── default_tools.xml         # register tool definitions
└── static/
    └── src/
        ├── components/
        │   ├── agent_chat_panel/  # OWL chat với tool call visualization
        │   │   ├── agent_chat_panel.js
        │   │   ├── agent_chat_panel.xml
        │   │   ├── tool_call_card.js  # hiển thị tool call + result
        │   │   ├── tool_call_card.xml
        │   │   ├── approval_dialog.js  # popup approve/reject
        │   │   └── approval_dialog.xml
        │   └── agent_audit_panel/
        │       ├── agent_audit_panel.js
        │       └── agent_audit_panel.xml
        └── agent_bus_service.js
```

---

## 4. __manifest__.py

```python
{
    'name': 'AI Agent',
    'version': '18.0.1.0.0',
    'summary': 'LLM agent that can act on Odoo with tool use + audit + HITL',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'category': 'Productivity/AI',
    'depends': [
        'ai_chatbot',        # Phase 1
        'ai_embedding',      # Phase 2
        'mail', 'bus', 'sale', 'product', 'account', 'stock',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/default_tools.xml',
        'views/ai_agent_pending_approval_views.xml',
        'views/ai_agent_audit_views.xml',
        'views/ai_agent_conversation_views.xml',
        'views/approve_wizard_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_agent/static/src/agent_bus_service.js',
            'ai_agent/static/src/components/agent_chat_panel/*',
            'ai_agent/static/src/components/agent_audit_panel/*',
        ],
    },
    'installable': True,
}
```

---

## 5. Service User + Auth model

**Critical:** tất cả tool execution chạy với dedicated user (KHÔNG dùng superuser, KHÔNG dùng `request.env.user`).

```python
# addons/custom/ai_agent/models/res_users.py
from odoo import api, fields, models, _


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _get_or_create_ai_service_user(self):
        """Singleton service user for AI tool execution."""
        user = self.search([('login', '=', 'ai_service')], limit=1)
        if not user:
            # Create user with restricted group
            ai_group = self.env.ref('ai_agent.group_ai_service')
            user = self.create({
                'name': 'AI Service User',
                'login': 'ai_service',
                'email': 'ai-service@odoo.local',
                'active': True,
                'share': False,
                'company_id': self.env.company.id,
                'company_ids': [(6, 0, self.env.company.ids)],
                'groups_id': [(6, 0, [ai_group.id])],
            })
        return user
```

```xml
<!-- addons/custom/ai_agent/security/security.xml -->
<odoo>
<data noupdate="1">
    <record id="module_category_ai_agent" model="ir.module.category">
        <field name="name">AI Agent</field>
    </record>

    <record id="group_ai_user" model="res.groups">
        <field name="name">AI Agent / User</field>
        <field name="category_id" ref="module_category_ai_agent"/>
    </record>

    <record id="group_ai_service" model="res.groups">
        <field name="name">AI Agent / Service Account</field>
        <field name="category_id" ref="module_category_ai_agent"/>
        <field name="comment">
            Dedicated group for the AI service user. 
            Grant only the model access needed for tool execution.
        </field>
    </record>

    <record id="group_ai_manager" model="res.groups">
        <field name="name">AI Agent / Manager</field>
        <field name="category_id" ref="module_category_ai_agent"/>
        <field name="implied_ids" eval="[(4, ref('group_ai_user'))]"/>
        <field name="users" eval="[(4, ref('base.user_admin'))]"/>
    </record>
</data>
</odoo>
```

**Service user chỉ access được:**
- `ai.agent.conversation` (read/write own)
- `ai.agent.audit` (write only — never read)
- `res.partner`, `product.product`, `sale.order`, `account.move`, `stock.picking` — tùy tools
- KHÔNG có quyền: `res.users` (except own), `ir.config_parameter`, `mail.message` (write to channel only)

---

## 6. Tool Base + Registry

```python
# addons/custom/ai_agent/tools/base.py
import json
from abc import ABC, abstractmethod


class BaseTool(ABC):
    """Base class cho mọi tool.
    
    Mỗi tool khai báo:
    - name: tên unique
    - description: mô tả cho LLM
    - parameters: JSON Schema
    - risk_level: 'low' | 'medium' | 'high'
    - execute(): thực thi
    """
    name: str = ''
    description: str = ''
    parameters: dict = {}
    risk_level: str = 'low'  # low, medium, high

    @abstractmethod
    def execute(self, env, **kwargs) -> dict:
        """Run tool. env đã là service user env."""
        ...

    def to_openai_schema(self) -> dict:
        """Format cho OpenAI-compatible tool API."""
        return {
            'type': 'function',
            'function': {
                'name': self.name,
                'description': self.description,
                'parameters': self.parameters,
            },
        }

    def requires_approval(self) -> bool:
        return self.risk_level == 'high'
```

```python
# addons/custom/ai_agent/services/tool_dispatcher.py
import json
import logging
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Registry + executor for tools."""

    def __init__(self, env):
        self.env = env
        self._registry = {}
        self._register_defaults()

    def _register_defaults(self):
        from ..tools.sale_tools import (
            SearchSaleOrdersTool, CreateSaleOrderTool, ConfirmSaleOrderTool
        )
        from ..tools.product_tools import SearchProductsTool
        from ..tools.partner_tools import SearchPartnersTool, CreatePartnerTool
        from ..tools.account_tools import SearchInvoicesTool
        from ..tools.stock_tools import SearchStockTool

        for tool_cls in [
            SearchSaleOrdersTool, SearchProductsTool, SearchPartnersTool,
            SearchInvoicesTool, SearchStockTool,
            CreatePartnerTool,          # medium risk
            CreateSaleOrderTool,        # medium risk (draft only)
            ConfirmSaleOrderTool,       # high risk
        ]:
            instance = tool_cls()
            self._registry[instance.name] = instance

    def get_tool_schemas(self) -> list:
        """Return list of tool definitions for LLM."""
        return [t.to_openai_schema() for t in self._registry.values()]

    def dispatch(self, tool_name: str, arguments: dict) -> dict:
        """Execute tool. Service user env. With audit + ACL + error handling."""
        if tool_name not in self._registry:
            return {'error': f'Unknown tool: {tool_name}'}

        tool = self._registry[tool_name]
        try:
            # Validate params against schema
            self._validate_params(tool, arguments)

            # Execute with service user env
            result = tool.execute(self.env, **arguments)

            # Audit log
            self.env['ai.agent.audit'].sudo().create({
                'tool_name': tool_name,
                'arguments': json.dumps(arguments),
                'result': json.dumps(result, default=str)[:8000],
                'success': True,
                'risk_level': tool.risk_level,
            })

            return result
        except (UserError, AccessError) as e:
            _logger.warning(f"Tool {tool_name} failed: {e}")
            self.env['ai.agent.audit'].sudo().create({
                'tool_name': tool_name,
                'arguments': json.dumps(arguments),
                'result': str(e)[:8000],
                'success': False,
                'risk_level': tool.risk_level,
            })
            return {'error': str(e)}
        except Exception as e:
            _logger.exception(f"Tool {tool_name} crashed")
            return {'error': f'Internal error: {e}'}

    def _validate_params(self, tool, arguments):
        """Basic JSON Schema validation."""
        schema = tool.parameters
        required = schema.get('required', [])
        for r in required:
            if r not in arguments:
                raise UserError(f"Missing required parameter: {r}")
```

---

## 7. Example tools

```python
# addons/custom/ai_agent/tools/sale_tools.py
from odoo.exceptions import UserError
from .base import BaseTool


class SearchSaleOrdersTool(BaseTool):
    name = 'search_sale_orders'
    description = ('Search sale orders by partner name, state, or date range. '
                   'Returns list of order ID, name, partner, amount, state.')
    parameters = {
        'type': 'object',
        'properties': {
            'partner_name': {'type': 'string', 'description': 'Filter by customer name (partial match)'},
            'state': {'type': 'string', 'enum': ['draft', 'sent', 'sale', 'done', 'cancel']},
            'date_from': {'type': 'string', 'description': 'ISO date YYYY-MM-DD'},
            'date_to': {'type': 'string', 'description': 'ISO date YYYY-MM-DD'},
            'limit': {'type': 'integer', 'default': 10, 'maximum': 50},
        },
    }
    risk_level = 'low'

    def execute(self, env, partner_name=None, state=None, date_from=None, date_to=None, limit=10, **kwargs):
        domain = []
        if partner_name:
            domain.append(('partner_id.name', 'ilike', partner_name))
        if state:
            domain.append(('state', '=', state))
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))

        orders = env['sale.order'].search(domain, limit=limit, order='date_order desc')
        return {
            'count': len(orders),
            'orders': [
                {
                    'id': o.id,
                    'name': o.name,
                    'partner': o.partner_id.name,
                    'amount': o.amount_total,
                    'state': o.state,
                    'date': str(o.date_order.date()),
                }
                for o in orders
            ],
        }


class CreateSaleOrderTool(BaseTool):
    name = 'create_sale_order'
    description = ('Create a DRAFT sale order for a customer with given products. '
                   'Does NOT confirm — user must approve confirmation separately.')
    parameters = {
        'type': 'object',
        'properties': {
            'partner_id': {'type': 'integer', 'description': 'res.partner ID'},
            'lines': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'product_id': {'type': 'integer'},
                        'quantity': {'type': 'number', 'minimum': 0.01},
                    },
                    'required': ['product_id', 'quantity'],
                },
            },
        },
        'required': ['partner_id', 'lines'],
    }
    risk_level = 'medium'  # creates draft, doesn't auto-confirm

    def execute(self, env, partner_id, lines, **kwargs):
        partner = env['res.partner'].browse(partner_id)
        if not partner.exists():
            raise UserError(f"Partner {partner_id} not found")

        order = env['sale.order'].create({
            'partner_id': partner_id,
            'state': 'draft',
        })
        for line in lines:
            product = env['product.product'].browse(line['product_id'])
            if not product.exists():
                order.unlink()
                raise UserError(f"Product {line['product_id']} not found")
            env['sale.order.line'].create({
                'order_id': order.id,
                'product_id': line['product_id'],
                'product_uom_qty': line['quantity'],
            })

        return {
            'order_id': order.id,
            'name': order.name,
            'amount': order.amount_total,
            'state': order.state,
            'message': f'Created draft SO {order.name}. User must approve to confirm.',
        }


class ConfirmSaleOrderTool(BaseTool):
    name = 'confirm_sale_order'
    description = 'Confirm a DRAFT sale order. Triggers availability check + creates picking.'
    parameters = {
        'type': 'object',
        'properties': {
            'order_id': {'type': 'integer'},
        },
        'required': ['order_id'],
    }
    risk_level = 'high'  # affects inventory + accounting downstream

    def execute(self, env, order_id, **kwargs):
        order = env['sale.order'].browse(order_id)
        if not order.exists():
            raise UserError(f"Order {order_id} not found")
        if order.state != 'draft':
            raise UserError(f"Order {order.name} is in state {order.state}, not draft")

        order.action_confirm()
        return {
            'order_id': order.id,
            'name': order.name,
            'state': order.state,
            'picking_ids': order.picking_ids.ids,
        }
```

**Cấu trúc tương tự cho:**
- `product_tools.py`: SearchProducts, GetProductInfo
- `partner_tools.py`: SearchPartners, CreatePartner (medium risk)
- `account_tools.py`: SearchInvoices (read-only, low risk)
- `stock_tools.py`: SearchStock, CreatePicking (medium risk), ValidatePicking (high risk)

---

## 8. Agent controller — Main loop

```python
# addons/custom/ai_agent/controllers/agent_controller.py
import json
import logging
from odoo import http, _, tools
from odoo.http import request
from odoo.addons.bus.models.bus import Bus

_logger = logging.getLogger(__name__)


class AIAgentController(http.Controller):

    @http.route('/ai_agent/chat', type='json', auth='user', csrf=False)
    def chat(self, channel_id, message, conversation_id=None, **kwargs):
        """User gửi message → agent loop → response (có thể kèm tool calls)."""
        Channel = request.env['discuss.channel']
        channel = Channel.browse(channel_id)
        if not channel.exists():
            return {'error': _('Channel not found')}

        # Get or create conversation
        Conversation = request.env['ai.agent.conversation']
        if conversation_id:
            conv = Conversation.browse(conversation_id)
        else:
            conv = Conversation.create({
                'channel_id': channel_id,
                'user_id': request.env.user.id,
            })

        # Save user message
        conv.add_message('user', message)

        # Build messages list (system + history + new)
        history = conv.get_messages_for_llm()
        tools = request.env['ai.agent.conversation']._get_tool_schemas()
        messages = [
            {'role': 'system', 'content': self._build_system_prompt(tools)},
        ] + history

        # === AGENT LOOP (max 5 iterations to prevent infinite) ===
        MAX_ITERATIONS = 5
        iteration = 0
        pending_approvals = []
        final_text = ''

        service_user = request.env['res.users'].sudo()._get_or_create_ai_service_user()

        while iteration < MAX_ITERATIONS:
            iteration += 1
            # Get LLM response (with tool calls)
            client = request.env['ai.agent.conversation']._get_agent_client()
            try:
                with request.env.cr.savepoint():
                    response = client.chat_with_tools(messages, tools)
            except Exception as e:
                _logger.exception("LLM call failed")
                return {'error': str(e)}

            # Add LLM response to messages
            llm_msg = {
                'role': 'assistant',
                'content': response.content or '',
            }
            if response.tool_calls:
                llm_msg['tool_calls'] = [
                    {'id': tc['id'], 'type': 'function', 'function': tc}
                    for tc in response.tool_calls
                ]
            messages.append(llm_msg)
            conv.add_message('assistant', response.content, tool_calls=response.tool_calls)

            # If no tool calls, done
            if not response.tool_calls:
                final_text = response.content
                break

            # Execute each tool call
            for tc in response.tool_calls:
                tool_name = tc['name']
                tool_args = json.loads(tc['arguments']) if isinstance(tc['arguments'], str) else tc['arguments']

                # Get tool object to check risk
                dispatcher = self._get_dispatcher()
                tool = dispatcher._registry.get(tool_name)
                if not tool:
                    tool_result = {'error': f'Unknown tool: {tool_name}'}
                elif tool.requires_approval():
                    # === HIGH-RISK: create pending approval, don't execute ===
                    approval = request.env['ai.agent.pending_approval'].sudo().create({
                        'conversation_id': conv.id,
                        'tool_name': tool_name,
                        'tool_arguments': json.dumps(tool_args),
                        'tool_call_id': tc['id'],
                        'state': 'pending',
                        'risk_description': tool.description,
                        'user_id': request.env.user.id,
                    })
                    pending_approvals.append(approval.id)
                    # Notify user via bus
                    Bus().sendone(
                        f'ai_agent_user_{request.env.user.id}',
                        {
                            'type': 'pending_approval',
                            'approval_id': approval.id,
                            'tool_name': tool_name,
                            'description': tool_args,
                        },
                    )
                    # Tell LLM the tool is awaiting approval
                    tool_result = {
                        'status': 'awaiting_approval',
                        'approval_id': approval.id,
                        'message': f'Tool {tool_name} cần user approval. Đợi user xác nhận.',
                    }
                else:
                    # === LOW/MEDIUM RISK: execute immediately with service user env ===
                    with request.env.cr.savepoint():
                        ServiceEnv = request.env(user=service_user)
                        # Re-create dispatcher with service env
                        service_dispatcher = type(dispatcher)(ServiceEnv)
                        tool_result = service_dispatcher.dispatch(tool_name, tool_args)

                # Add tool result to messages
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tc['id'],
                    'content': json.dumps(tool_result, default=str),
                })
                conv.add_message('tool', json.dumps(tool_result), tool_call_id=tc['id'])

            # Loop: LLM sees tool results, may call more tools or finalize

        # Post final response to channel
        if final_text:
            channel.message_post(
                body=final_text,
                message_type='comment',
                author_id=channel.sudo()._get_ai_partner_id(),
            )

        return {
            'conversation_id': conv.id,
            'response': final_text,
            'pending_approvals': pending_approvals,
            'iterations': iteration,
        }

    def _build_system_prompt(self, tools):
        tool_list = "\n".join(f"- {t['function']['name']}: {t['function']['description']}" for t in tools)
        return f"""Bạn là AI Agent cho hệ thống Odoo ERP.

Bạn có các tools sau:
{tool_list}

Quy tắc:
- Sử dụng tools khi cần thiết, không bịa thông tin
- Nếu cần tạo/sửa data nhạy cảm, tool sẽ yêu cầu user approval
- Trả lời ngắn gọn, bằng tiếng Việt nếu user dùng tiếng Việt
- Sau khi hoàn thành task, tóm tắt kết quả cho user"""

    def _get_dispatcher(self):
        from ..services.tool_dispatcher import ToolDispatcher
        return ToolDispatcher(request.env)

    @http.route('/ai_agent/approve', type='json', auth='user', csrf=False)
    def approve(self, approval_id, **kwargs):
        """User approves pending action → execute tool."""
        approval = request.env['ai.agent.pending_approval'].browse(approval_id)
        if not approval.exists() or approval.state != 'pending':
            return {'error': 'Approval not found or not pending'}
        if approval.user_id != request.env.user:
            return {'error': 'You cannot approve this action'}

        # Execute tool with service user
        service_user = request.env['res.users'].sudo()._get_or_create_ai_service_user()
        ServiceEnv = request.env(user=service_user)
        from ..services.tool_dispatcher import ToolDispatcher
        dispatcher = ToolDispatcher(ServiceEnv)

        tool_args = json.loads(approval.tool_arguments)
        result = dispatcher.dispatch(approval.tool_name, tool_args)

        approval.write({
            'state': 'approved',
            'approved_by': request.env.user.id,
            'approve_date': fields.Datetime.now(),
            'result': json.dumps(result, default=str)[:8000],
        })

        # Resume conversation: feed result back to LLM
        conv = approval.conversation_id
        llm_msg = {
            'role': 'tool',
            'tool_call_id': approval.tool_call_id,
            'content': json.dumps(result, default=str),
        }
        # Run another agent loop iteration with this tool result
        ...

        return {'status': 'approved', 'result': result}

    @http.route('/ai_agent/reject', type='json', auth='user', csrf=False)
    def reject(self, approval_id, reason='', **kwargs):
        approval = request.env['ai.agent.pending_approval'].browse(approval_id)
        if not approval.exists() or approval.state != 'pending':
            return {'error': 'Approval not found'}
        if approval.user_id != request.env.user:
            return {'error': 'You cannot reject this action'}

        approval.write({
            'state': 'rejected',
            'rejected_by': request.env.user.id,
            'reject_reason': reason,
        })
        return {'status': 'rejected'}
```

---

## 9. Pending Approval model + UI

```python
# addons/custom/ai_agent/models/ai_agent_pending_approval.py
from odoo import fields, models, _


class AIAgentPendingApproval(models.Model):
    _name = 'ai.agent.pending_approval'
    _description = 'AI Agent Action Awaiting Human Approval'
    _order = 'create_date desc'

    conversation_id = fields.Many2one('ai.agent.conversation', required=True, ondelete='cascade')
    tool_name = fields.Char(required=True, index=True)
    tool_arguments = fields.Text(required=True)
    tool_call_id = fields.Char(required=True)
    risk_description = fields.Text()
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', required=True, index=True)
    user_id = fields.Many2one('res.users', required=True, help='User who triggered the action')
    approved_by = fields.Many2one('res.users')
    approve_date = fields.Datetime()
    rejected_by = fields.Many2one('res.users')
    reject_reason = fields.Text()
    result = fields.Text()
    create_date = fields.Datetime(default=fields.Datetime.now, index=True)
```

```xml
<!-- addons/custom/ai_agent/views/ai_agent_pending_approval_views.xml -->
<record id="view_ai_agent_pending_approval_tree" model="ir.ui.view">
    <field name="name">ai.agent.pending.approval.tree</field>
    <field name="model">ai.agent.pending_approval</field>
    <field name="arch" type="xml">
        <tree decoration-warning="state=='pending'" decoration-success="state=='approved'" decoration-danger="state=='rejected'">
            <field name="create_date"/>
            <field name="user_id"/>
            <field name="tool_name"/>
            <field name="state"/>
        </tree>
    </field>
</record>

<record id="view_ai_agent_pending_approval_form" model="ir.ui.view">
    <field name="name">ai.agent.pending.approval.form</field>
    <field name="model">ai.agent.pending_approval</field>
    <field name="arch" type="xml">
        <form>
            <header>
                <button name="action_approve" type="object" string="Approve" class="btn-primary" invisible="state!='pending'"/>
                <button name="action_reject" type="object" string="Reject" class="btn-danger" invisible="state!='pending'"/>
                <field name="state" widget="statusbar"/>
            </header>
            <sheet>
                <group>
                    <field name="user_id" readonly="True"/>
                    <field name="tool_name" readonly="True"/>
                    <field name="risk_description" readonly="True"/>
                    <field name="create_date" readonly="True"/>
                </group>
                <group string="Tool Arguments (JSON)">
                    <field name="tool_arguments" readonly="True" widget="ace" options="{'mode': 'json'}"/>
                </group>
                <group string="Result" invisible="not result">
                    <field name="result" readonly="True" widget="ace" options="{'mode': 'json'}"/>
                </group>
            </sheet>
        </form>
    </field>
</record>

<record id="action_ai_agent_pending_approval" model="ir.actions.act_window">
    <field name="name">Pending AI Approvals</field>
    <field name="res_model">ai.agent.pending_approval</field>
    <field name="view_mode">tree,form</field>
    <field name="domain">[('state', '=', 'pending'), ('user_id', '=', uid)]</field>
</record>

<menuitem id="menu_ai_agent_approvals" name="Pending Approvals" parent="ai_chatbot.menu_ai_chatbot_root" action="action_ai_agent_pending_approval" sequence="20" groups="ai_agent.group_ai_user"/>
```

---

## 10. Audit Log

```python
# addons/custom/ai_agent/models/ai_agent_audit.py
from odoo import fields, models, _


class AIAgentAudit(models.Model):
    _name = 'ai.agent.audit'
    _description = 'AI Agent Audit Log'
    _order = 'create_date desc'
    _log_access = False

    create_date = fields.Datetime(default=fields.Datetime.now, index=True)
    create_uid = fields.Many2one('res.users', default=lambda s: s.env.uid, index=True)
    conversation_id = fields.Many2one('ai.agent.conversation', index=True)
    tool_name = fields.Char(required=True, index=True)
    arguments = fields.Text()
    result = fields.Text()
    success = fields.Boolean(index=True)
    risk_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], index=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, index=True)

    def init(self):
        # Auto-cleanup: giữ 90 ngày
        from datetime import datetime, timedelta
        cutoff = fields.Datetime.to_string(datetime.now() - timedelta(days=90))
        self.env.cr.execute("DELETE FROM ai_agent_audit WHERE create_date < %s", (cutoff,))
```

```xml
<!-- ACL: service user write-only, manager read-only -->
<record id="access_ai_agent_audit_service" model="ir.model.access">
    <field name="name">ai.agent.audit.service</field>
    <field name="model_id" ref="model_ai_agent_audit"/>
    <field name="group_id" ref="ai_agent.group_ai_service"/>
    <field name="perm_read">0</field>
    <field name="perm_write">1</field>
    <field name="perm_create">1</field>
    <field name="perm_unlink">0</field>
</record>

<record id="access_ai_agent_audit_manager" model="ir.model.access">
    <field name="name">ai.agent.audit.manager</field>
    <field name="model_id" ref="model_ai_agent_audit"/>
    <field name="group_id" ref="ai_agent.group_ai_manager"/>
    <field name="perm_read">1</field>
    <field name="perm_write">0</field>
    <field name="perm_create">0</field>
    <field name="perm_unlink">0</field>
</record>
```

---

## 11. Frontend — Tool Call Visualization

```js
/** @odoo-module **/
// addons/custom/ai_agent/static/src/components/agent_chat_panel/tool_call_card.js

import { Component } from "@odoo/owl";


export class ToolCallCard extends Component {
    static template = "ai_agent.ToolCallCard";
    static props = {
        toolCall: { type: Object },
        result: { type: Object, optional: true },
    };

    get statusClass() {
        if (!this.props.result) return 'o_tool_card_running';
        if (this.props.result.error) return 'o_tool_card_error';
        if (this.props.result.status === 'awaiting_approval') return 'o_tool_card_pending';
        return 'o_tool_card_success';
    }

    get prettyArgs() {
        return JSON.stringify(this.props.toolCall.arguments, null, 2);
    }

    get prettyResult() {
        if (!this.props.result) return null;
        return JSON.stringify(this.props.result, null, 2);
    }
}
```

```xml
<t t-name="ai_agent.ToolCallCard">
    <div t-attf-class="o_tool_call_card {{ statusClass }}">
        <div class="o_tool_card_header">
            <i t-attf-class="fa {{ 
                statusClass === 'o_tool_card_pending' ? 'fa-clock-o' :
                statusClass === 'o_tool_card_error' ? 'fa-times-circle' :
                statusClass === 'o_tool_card_running' ? 'fa-spinner fa-spin' :
                'fa-check-circle'
            }}"/>
            <span t-esc="props.toolCall.name"/>
        </div>
        <details>
            <summary>Arguments</summary>
            <pre t-esc="prettyArgs"/>
        </details>
        <details t-if="prettyResult">
            <summary>Result</summary>
            <pre t-esc="prettyResult"/>
        </details>
    </div>
</t>
```

---

## 12. Settings UI

```python
# addons/custom/ai_agent/models/res_config_settings.py
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_agent_enabled = fields.Boolean(
        string='Enable AI Agent',
        config_parameter='ai_agent.enabled',
        default=True,
    )
    ai_agent_max_iterations = fields.Integer(
        string='Max Agent Loop Iterations',
        config_parameter='ai_agent.max_iterations',
        default=5,
    )
    ai_agent_audit_retention_days = fields.Integer(
        string='Audit Log Retention (days)',
        config_parameter='ai_agent.audit_retention_days',
        default=90,
    )
    ai_agent_require_approval_above = fields.Selection([
        ('low', 'Low (everything requires approval)'),
        ('medium', 'Medium (only high-risk requires approval)'),
        ('high', 'High (no approval needed)'),
    ], string='Require Approval Above',
       config_parameter='ai_agent.require_approval_above',
       default='high')
```

---

## 13. Deployment steps

```bash
# 1. Install module
./scripts/cli.sh -d odoo_dev -i ai_agent --stop-after-init
docker compose restart odoo

# 2. Verify AI Service User created
./scripts/cli.sh shell -d odoo_dev <<EOF
user = env['res.users']._get_or_create_ai_service_user()
print(f"Service user: {user.name} (id={user.id})")
EOF

# 3. Test tool execution
# Settings → AI Agent → enable
# Discuss → channel → enable agent mode
# Gõ: "Tìm đơn hàng của khách Minh Tuấn"
# → Agent call search_sale_orders tool, return results
# Gõ: "Tạo đơn cho khách đó, 5 áo thun"
# → Agent call create_sale_order (medium risk) → auto-execute
# Gõ: "Xác nhận đơn vừa tạo"
# → Agent call confirm_sale_order (high risk) → pending approval → popup
```

---

## 14. Acceptance criteria

- [ ] Module install OK, AI Service User created
- [ ] Agent chat responds với tool calls (use MiniMax with tool use — verify)
- [ ] Read-only tools (search, get) auto-execute
- [ ] Medium-risk tools (create draft) auto-execute + audit log
- [ ] High-risk tools (confirm) tạo pending_approval + bus notify
- [ ] User click Approve → tool executes + state='approved'
- [ ] User click Reject → state='rejected', no execution
- [ ] `ai.agent.audit` có entries cho mọi tool call
- [ ] Audit log tự động cleanup sau 90 ngày
- [ ] Multi-company: agent từ company A không thấy data company B
- [ ] Agent loop terminates (max 5 iterations, không infinite)
- [ ] OWL UI shows tool call cards với args + result
- [ ] Pending approval popup appears trong UI

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| MiniMax không hỗ trợ tool use | Fallback OpenAI/Ollama cho agent; code abstraction đã có |
| LLM infinite loop (gọi tool liên tục) | MAX_ITERATIONS=5 hard cap |
| LLM gọi tool sai args → data corruption | JSON Schema validation; tool sandbox (try/except) |
| Service user quá rộng quyền → privilege escalation | Chỉ grant access cần thiết cho tools; manual test từng tool |
| Prompt injection qua user input → execute tool ngoài ý muốn | System prompt cứng; user input KHÔNG thành system role; HITL cho high-risk |
| HITL bypass nếu agent trigger nhiều approval cùng lúc | UI batch approval; hoặc quota per session |
| Audit log spam khi gọi tool nhiều | Retention 90 ngày + có thể adjust |

---

## 16. Deliverables

1. Module `addons/custom/ai_agent/` — installable, tested
2. AI Service User + groups setup
3. Tool framework (BaseTool, ToolDispatcher)
4. 9+ tools: search/create/confirm cho sale, product, partner, account, stock
5. Agent controller với loop + tool execution
6. Pending approval model + UI
7. Audit log + auto-cleanup
8. OWL UI: tool call cards, approval dialog
9. Settings: enable, max iter, retention, approval threshold
10. Tests: tool unit tests, agent loop test, ACL test, HITL test
11. Docs + security review

---

## 17. Effort estimate

- Tool framework + dispatcher: 2-3 ngày
- 9+ tool implementations: 4-5 ngày
- AI Service User + ACL setup: 1 ngày
- Agent controller + loop: 3-4 ngày
- Pending approval model + UI: 2-3 ngày
- Audit log + cleanup: 1 ngày
- OWL frontend (tool cards, approval dialog): 3-4 ngày
- Settings + integration: 1-2 ngày
- Tests: 3-4 ngày
- Security review: 1-2 ngày
- Docs: 1 ngày
- **Total: 22-30 ngày (4-6 tuần)**

---

## 18. Next phase

Sau khi Phase 3 production-ready → chuyển sang [Phase 4: Advanced](./proposal-phase4-advanced.md)
