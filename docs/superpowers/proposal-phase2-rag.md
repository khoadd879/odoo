# Phase 2 Proposal — RAG (Retrieval-Augmented Generation)

**Date:** 2026-06-08
**Duration:** 2-3 tuần
**Module mới:** `addons/custom/ai_embedding/`
**Depends on:** `queue_job` (OCA/server-tools), `mail`, `ai_chatbot` (từ Phase 1)
**Output:** Chatbot Phase 1 tự động retrieve context từ Odoo data trước khi gọi LLM; trả lời chính xác + trích dẫn nguồn

---

## 1. Goal

Khi user hỏi chatbot, hệ thống tự tìm trong Odoo data (products, sale orders, knowledge articles, mail messages...) các chunks liên quan, inject vào LLM prompt, để câu trả lời dựa trên dữ liệu thật với citation nguồn.

**Critical:** tôn trọng ACL — user chỉ thấy chunks từ records họ có quyền đọc.

---

## 2. LLM Provider — MiniMax (cho embedding)

Cần verify với user:
- **Embedding model name** (vd `minimax-embedding-01`? OpenAI-compatible endpoint?)
- **Embedding dimensions** (768? 1024? 1536? — ảnh hưởng vector storage sizing)
- **Batch size** cho multi-chunk embed
- **Cost** per 1M tokens

**Strategy:** dùng embedding model từ MiniMax nếu multi-language tốt (Vietnamese + English). Nếu không → fallback BGE-M3 local qua Ollama (`nomic-embed-text`).

**Abstraction (mở rộng từ Phase 1):**

```python
# addons/custom/ai_embedding/services/embedding_client.py
class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return list of vectors, same order as input."""
        ...
    @property
    @abstractmethod
    def dimensions(self) -> int: ...


class MinimaxEmbeddings(EmbeddingClient):
    """MiniMax embedding API."""
    def __init__(self, api_key, base_url, model):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def embed(self, texts):
        # TODO: verify với MiniMax docs
        resp = requests.post(
            f'{self.base_url}/embeddings',
            headers={'Authorization': f'Bearer {self.api_key}'},
            json={'model': self.model, 'input': texts},
            timeout=60,
        )
        resp.raise_for_status()
        return [d['embedding'] for d in resp.json()['data']]

    @property
    def dimensions(self):
        # TODO: verify với MiniMax model card
        return 1024  # placeholder


class OllamaEmbeddings(EmbeddingClient):
    """Local fallback. nomic-embed-text = 768d, multilingual-e5 = 1024d."""
    def __init__(self, base_url='http://ollama:11434', model='nomic-embed-text'):
        self.base_url = base_url
        self.model = model

    def embed(self, texts):
        # Ollama embed 1 by 1 (no batch endpoint)
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text):
        resp = requests.post(
            f'{self.base_url}/api/embeddings',
            json={'model': self.model, 'prompt': text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()['embedding']

    @property
    def dimensions(self):
        return 768 if 'nomic' in self.model else 1024
```

---

## 3. Module structure

```
addons/custom/ai_embedding/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── search_controller.py     # /ai/search (semantic search + ACL)
├── models/
│   ├── __init__.py
│   ├── ai_embedding.py          # model chính
│   ├── res_config_settings.py   # settings: vector store, embedding model
│   ├── product_product.py       # _inherit: write hook
│   ├── sale_order.py            # _inherit
│   ├── account_move.py          # _inherit
│   ├── knowledge_article.py     # _inherit (nếu có knowledge module)
│   ├── mail_message.py          # _inherit (optional)
│   └── res_partner.py           # _inherit
├── services/
│   ├── __init__.py
│   ├── embedding_client.py      # base + MiniMax + Ollama
│   ├── chunker.py               # text chunking strategy
│   └── pgvector_store.py        # pgvector operations
├── jobs/
│   ├── __init__.py
│   └── embedding_job.py         # queue_job handler
├── data/
│   ├── ai_embedding_cron.xml    # cron re-embed dirty
│   └── default_config.xml
├── migrations/
│   └── 18.0.1.0/
│       └── post-migrate.py      # CREATE EXTENSION pgvector
├── views/
│   ├── ai_embedding_views.xml   # tree/form for embeddings admin
│   └── res_config_settings_views.xml
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
└── tests/
    ├── test_embedding.py
    ├── test_search_acl.py
    └── test_chunker.py
```

---

## 4. __manifest__.py

```python
{
    'name': 'AI Embedding & RAG',
    'version': '18.0.1.0.0',
    'summary': 'Embed Odoo records into pgvector, semantic search with ACL',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'category': 'Productivity/AI',
    'depends': [
        'queue_job',        # OCA/server-tools
        'mail',
        'product',
        'sale',
        'account',
        'ai_chatbot',       # Phase 1 module
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/default_config.xml',
        'data/ai_embedding_cron.xml',
        'views/ai_embedding_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}
```

---

## 5. Database — pgvector setup

**Postgres 16 đã có sẵn `pgvector` extension** (built-in). Cần enable lúc migration.

```python
# addons/custom/ai_embedding/migrations/18.0.1.0/post-migrate.py
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    _logger.info("pgvector extension enabled")

    # Vector column — dimension phải match embedding model
    # Mặc định 1024 (configurable nếu đổi model sau)
    cr.execute("""
        ALTER TABLE ai_embedding
        ADD COLUMN IF NOT EXISTS vector vector(1024);
    """)
    _logger.info("ai_embedding.vector column ensured")

    # HNSW index cho ANN search
    cr.execute("""
        CREATE INDEX IF NOT EXISTS ai_embedding_vector_hnsw_idx
        ON ai_embedding
        USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    _logger.info("HNSW index created on ai_embedding.vector")
```

**Why HNSW, not IVF?** HNSW tốt hơn cho <1M vectors, không cần training, query latency thấp hơn. Scale >10M mới cần IVF.

---

## 6. Core model — `ai.embedding`

```python
# addons/custom/ai_embedding/models/ai_embedding.py
import hashlib
import json
import logging

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AIEmbedding(models.Model):
    _name = 'ai.embedding'
    _description = 'Vector Embedding of Odoo Records'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    res_model = fields.Char(string='Source Model', required=True, index=True)
    res_id = fields.Integer(string='Source Record ID', required=True, index=True)
    chunk_index = fields.Integer(string='Chunk Index', default=0)
    chunk_text = fields.Text(string='Chunk Text', required=True)
    chunk_hash = fields.Char(string='Chunk Hash', size=64, index=True,
                             help='SHA256 of chunk_text — used for invalidation')
    embedding_model = fields.Char(string='Embedding Model', required=True,
                                  help='e.g. minimax-embedding-01, nomic-embed-text')
    vector = fields.Binary(string='Vector', attachment=False,
                           help='Serialized float32 array (pgvector stores natively)')
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, index=True)
    user_id = fields.Many2one('res.users', default=lambda s: s.env.user,
                              help='Owner of source record (for ACL)')
    create_date = fields.Datetime(default=fields.Datetime.now, index=True)
    write_date = fields.Datetime(default=fields.Datetime.now)

    # SQL-level vector (pgvector native)
    _sql_constraints = [
        ('unique_chunk', 'UNIQUE(res_model, res_id, chunk_index, embedding_model)',
         'Duplicate embedding chunk'),
    ]

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('res_model', 'res_id', 'chunk_index')
    def _compute_display_name(self):
        for r in self:
            r.display_name = f"{r.res_model}#{r.res_id} chunk {r.chunk_index}"

    # === Write hooks (chunks invalidate on hash mismatch) ===

    @api.model
    def _embed_record(self, record):
        """Chunk + embed a record. Idempotent (skip if hash unchanged)."""
        self.ensure_one()  # not really, called on record, not embedding
        ...

    # === Search — ACL enforced ===

    def _search_similar(self, query_vector, model=None, limit=5, min_score=0.7):
        """Semantic search with ACL filter.
        
        Critical: phải filter kết quả qua env[model].search() để apply record rules.
        """
        # 1. Raw vector search (no ACL) — get top K*20 candidates
        candidates = self._raw_pgvector_search(
            query_vector, model=model, limit=limit * 20,
        )
        if not candidates:
            return []

        # 2. Group by res_model → batch search through ORM
        from collections import defaultdict
        by_model = defaultdict(list)
        for c in candidates:
            by_model[c['res_model']].append(c['res_id'])

        # 3. Filter qua ORM (honors record rules + multi-company)
        accessible = []
        for res_model, res_ids in by_model.items():
            Model = self.env[res_model]
            try:
                allowed_ids = set(Model.search([('id', 'in', res_ids)]).ids)
            except Exception:
                _logger.warning(f"Cannot search {res_model} for ACL check", exc_info=True)
                continue
            for c in candidates:
                if c['res_model'] == res_model and c['res_id'] in allowed_ids:
                    accessible.append(c)

        # 4. Re-rank by score, slice top K
        accessible.sort(key=lambda c: c['score'], reverse=True)
        return accessible[:limit]

    def _raw_pgvector_search(self, query_vector, model=None, limit=10):
        """Raw SQL cosine similarity search (no ACL)."""
        self.env.cr.execute("""
            SELECT id, res_model, res_id, chunk_index, chunk_text,
                   1 - (vector <=> %s::vector) AS score
            FROM ai_embedding
            WHERE (%s IS NULL OR res_model = %s)
              AND company_id = %s
            ORDER BY vector <=> %s::vector
            LIMIT %s
        """, (
            query_vector,
            model, model,
            self.env.company.id,
            query_vector,
            limit,
        ))
        return self.env.cr.dictfetchall()

    # === Embedding pipeline ===

    @api.model
    def _fetch_embedding(self, text):
        """Call active embedding client."""
        client = self._get_embedding_client()
        return client.embed([text])[0]

    @api.model
    def _get_embedding_client(self):
        ICP = self.env['ir.config_parameter'].sudo()
        provider = ICP.get_param('ai_embedding.provider', 'minimax')

        if provider == 'minimax':
            from ..services.embedding_client import MinimaxEmbeddings
            return MinimaxEmbeddings(
                api_key=ICP.get_param('ai_embedding.minimax_api_key', ''),
                base_url=ICP.get_param('ai_embedding.minimax_base_url', 'https://api.minimax.chat/v1'),
                model=ICP.get_param('ai_embedding.minimax_model', ''),
            )
        elif provider == 'ollama':
            from ..services.embedding_client import OllamaEmbeddings
            return OllamaEmbeddings(
                base_url=ICP.get_param('ai_embedding.ollama_url', 'http://ollama:11434'),
                model=ICP.get_param('ai_embedding.ollama_model', 'nomic-embed-text'),
            )
        raise ValueError(f"Unknown embedding provider: {provider}")
```

---

## 7. Write hooks — auto-embed on record change

```python
# addons/custom/ai_embedding/models/product_product.py
import hashlib
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    ai_embedding_ids = fields.One2many('ai.embedding', compute='_compute_ai_embedding_ids')
    ai_embedding_dirty = fields.Boolean(default=False)

    def _compute_ai_embedding_ids(self):
        for r in self:
            r.ai_embedding_ids = self.env['ai.embedding'].search([
                ('res_model', '=', 'product.product'),
                ('res_id', '=', r.id),
            ])

    def _get_embedding_text(self):
        """Compose text to embed."""
        self.ensure_one()
        parts = [
            self.default_code or '',
            self.name or '',
            self.description_sale or '',
            f"Category: {self.categ_id.complete_name}" if self.categ_id else '',
            f"Price: {self.list_price} {self.currency_id.name}" if self.list_price else '',
        ]
        return ' | '.join(p for p in parts if p)

    def write(self, vals):
        result = super().write(vals)
        # Only re-embed if relevant fields changed
        watched = {'name', 'default_code', 'description_sale', 'categ_id', 'list_price'}
        if watched & set(vals.keys()):
            self._enqueue_embedding()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._enqueue_embedding()
        return records

    def _enqueue_embedding(self):
        """Async embed via queue_job (không block main thread)."""
        for r in self:
            r.with_delay(
                priority=5,
                description=f"Embed product {r.display_name}",
            )._action_embed()

    def _action_embed(self):
        """Actual embed work — runs in queue_job worker."""
        Embedding = self.env['ai.embedding']
        text = self._get_embedding_text()
        if not text.strip():
            return

        # Hash check — skip if unchanged
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        existing = Embedding.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('chunk_hash', '=', text_hash),
        ], limit=1)
        if existing:
            return

        # Delete old chunks (different hash)
        Embedding.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
        ]).unlink()

        # Chunk + embed
        chunks = self.env['ai.embedding']._chunk_text(text, max_tokens=512)
        embedding_model = self.env['ir.config_parameter'].sudo().get_param(
            'ai_embedding.model_name', 'minimax-embedding-01'
        )
        client = Embedding._get_embedding_client()
        vectors = client.embed(chunks)

        for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
            Embedding.create({
                'res_model': self._name,
                'res_id': self.id,
                'chunk_index': idx,
                'chunk_text': chunk,
                'chunk_hash': hashlib.sha256(chunk.encode()).hexdigest(),
                'embedding_model': embedding_model,
                'vector': json.dumps(vec),  # OR use raw SQL with vector type
                'company_id': self.env.company.id,
            })
```

**Pattern: tương tự cho `sale.order`, `account.move`, `res.partner`.** Mỗi model có `_get_embedding_text()` riêng để extract field phù hợp.

---

## 8. Chunker

```python
# addons/custom/ai_embedding/services/chunker.py
import re


def chunk_text(text, max_tokens=512, overlap=64, model='gpt-4'):
    """Naive chunker: split by sentences, accumulate to max_tokens.
    
    Tokens ≈ len(text) / 4 for English, / 2.5 for Vietnamese.
    Đơn giản hóa: dùng char count / 2.5.
    """
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []

    # Rough char/token ratio
    char_per_token = 2.5  # Vietnamese
    max_chars = int(max_tokens * char_per_token)
    overlap_chars = int(overlap * char_per_token)

    # Split by sentence (Vietnamese + English sentence delimiters)
    sentences = re.split(r'(?<=[.!?。])\s+', text)

    chunks = []
    current = ''
    for sent in sentences:
        if len(current) + len(sent) > max_chars and current:
            chunks.append(current.strip())
            # Overlap: keep last N chars
            current = current[-overlap_chars:] + ' ' + sent
        else:
            current = (current + ' ' + sent).strip()

    if current:
        chunks.append(current.strip())

    return chunks
```

**Sau này upgrade:** semantic chunking (LangChain `SemanticChunker`) — Phase 4.

---

## 9. RAG integration với Phase 1 chatbot

Modify `ai_chatbot/controllers/chatbot_controller.py` để retrieve context trước:

```python
# addons/custom/ai_chatbot/controllers/chatbot_controller.py (updated)
@http.route('/chatbot/ask', type='json', auth='user', csrf=False)
def ask(self, channel_id, message, **kwargs):
    channel = request.env['discuss.channel'].browse(channel_id)
    if not channel.exists():
        return {'error': _('Channel not found')}

    # === RAG step (new in Phase 2) ===
    rag_enabled = request.env['ir.config_parameter'].sudo().get_param(
        'ai_chatbot.rag_enabled', 'True'
    ) == 'True'
    context_chunks = []
    if rag_enabled:
        context_chunks = self._retrieve_context(message, limit=5, min_score=0.7)

    # === Build prompt with context ===
    system_prompt = self._build_system_prompt(channel, context_chunks)
    history = channel._get_chat_history(limit=20)
    messages = [
        {'role': 'system', 'content': system_prompt},
    ] + history + [{'role': 'user', 'content': message}]

    # === Call LLM (unchanged) ===
    try:
        client = request.env['chatbot.conversation']._get_llm_client()
        llm_response = client.chat(messages)
    except Exception as e:
        ...

    # === Post + add citations ===
    body = self._format_response_with_citations(llm_response, context_chunks)
    ai_msg = channel.message_post(body=body, ...)
    ...

def _retrieve_context(self, query, limit=5, min_score=0.7):
    """Embed query → semantic search → return top chunks."""
    Embedding = request.env['ai.embedding']
    try:
        query_vector = Embedding._fetch_embedding(query)
    except Exception as e:
        _logger.warning("Failed to embed query: %s", e)
        return []

    return Embedding._search_similar(
        query_vector, limit=limit, min_score=min_score,
    )

def _build_system_prompt(self, channel, context_chunks):
    base = request.env['ir.config_parameter'].sudo().get_param(
        'ai_chatbot.system_prompt',
        default='You are a helpful AI assistant for an Odoo ERP system. '
                'Answer in the same language as the user. Be concise. '
                'If you don\'t know, say so — do not invent.'
    )
    if not context_chunks:
        return base

    context_text = "\n\n".join(
        f"[Source {i+1}] ({c['res_model']}#{c['res_id']}, score {c['score']:.2f}):\n{c['chunk_text']}"
        for i, c in enumerate(context_chunks)
    )
    return f"""{base}

Bạn có context sau từ hệ thống Odoo (cite source ID khi dùng):

{context_text}

QUAN TRỌNG: chỉ trả lời dựa trên context trên. Nếu không tìm thấy, nói rõ "không có thông tin"."""

def _format_response_with_citations(self, response, chunks):
    if not chunks:
        return response
    citations = "\n\n📚 Nguồn: " + ", ".join(
        f"[{i+1}] {c['res_model']}#{c['res_id']}" for i, c in enumerate(chunks)
    )
    return response + citations
```

---

## 10. Cron — re-embed dirty records

```xml
<!-- addons/custom/ai_embedding/data/ai_embedding_cron.xml -->
<odoo>
<data noupdate="1">
    <record id="cron_ai_embedding_reindex" model="ir.cron">
        <field name="name">AI Embedding: Re-embed dirty records</field>
        <field name="model_id" ref="model_ai_embedding"/>
        <field name="state">code</field>
        <field name="code">model.cron_re_embed_dirty()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="numbercall">-1</field>
        <field name="active">True</field>
    </record>
</data>
</odoo>
```

```python
# In ai_embedding.py
@api.model
def cron_re_embed_dirty(self, batch_size=100):
    """Find records whose embedding hash no longer matches content hash, re-embed."""
    # Strategy: scan recently-changed records (write_date > last_embed)
    # Phase 2 simple version: re-embed all records modified in last 7 days
    # whose ai_embedding chunk_hash != current content hash
    
    ICP = self.env['ir.config_parameter'].sudo()
    models_to_scan = json.loads(ICP.get_param('ai_embedding.tracked_models', '[]'))
    if not models_to_scan:
        return
    
    cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=7)
    for model_name in models_to_scan:
        Model = self.env[model_name]
        # Records modified recently
        records = Model.search([('write_date', '>=', cutoff)], limit=batch_size)
        records._enqueue_embedding()  # hash check sẽ skip nếu unchanged
```

---

## 11. Settings UI

```python
# addons/custom/ai_embedding/models/res_config_settings.py
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_embedding_provider = fields.Selection([
        ('minimax', 'MiniMax'),
        ('ollama', 'Ollama (local)'),
    ], string='Embedding Provider', config_parameter='ai_embedding.provider', default='minimax')

    ai_embedding_minimax_api_key = fields.Char(config_parameter='ai_embedding.minimax_api_key')
    ai_embedding_minimax_base_url = fields.Char(
        config_parameter='ai_embedding.minimax_base_url',
        default='https://api.minimax.chat/v1',
    )
    ai_embedding_minimax_model = fields.Char(
        config_parameter='ai_embedding.minimax_model',
        default='minimax-embedding-01',
    )
    ai_embedding_ollama_url = fields.Char(
        config_parameter='ai_embedding.ollama_url',
        default='http://ollama:11434',
    )
    ai_embedding_ollama_model = fields.Char(
        config_parameter='ai_embedding.ollama_model',
        default='nomic-embed-text',
    )

    ai_embedding_tracked_models = fields.Char(
        config_parameter='ai_embedding.tracked_models',
        default='["product.product", "sale.order", "res.partner"]',
        help='JSON list of models to auto-embed',
    )
    ai_embedding_min_score = fields.Float(
        config_parameter='ai_embedding.min_score',
        default=0.7,
        help='Minimum cosine similarity (0-1) to include in results',
    )
```

---

## 12. Security

```csv
<!-- addons/custom/ai_embedding/security/ir.model.access.csv -->
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_ai_embedding_user,ai.embedding.user,model_ai_embedding,base.group_user,1,0,0,0
access_ai_embedding_manager,ai.embedding.manager,model_ai_embedding,ai_chatbot.group_chatbot_manager,1,1,1,1
```

**Critical:** regular user chỉ có `perm_read=1` trên `ai.embedding` — không thể xem/edit/delete trực tiếp. Search đi qua `_search_similar` (ACL-enforced method).

---

## 13. Tests

```python
# addons/custom/ai_embedding/tests/test_embedding.py
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAIEmbedding(TransactionCase):

    def setUp(self):
        super().setUp()
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'default_code': 'TP-001',
            'list_price': 100.0,
        })

    def test_write_hook_creates_embedding(self):
        """write() should enqueue embedding job."""
        # Trigger sync (force_delay=False for test)
        self.product.with_context(test_no_queue=True)._action_embed()
        embeddings = self.env['ai.embedding'].search([
            ('res_model', '=', 'product.product'),
            ('res_id', '=', self.product.id),
        ])
        self.assertGreater(len(embeddings), 0)

    def test_hash_invalidation(self):
        """If text unchanged, embedding not re-created."""
        self.product._action_embed()
        count_before = self.env['ai.embedding'].search_count([
            ('res_model', '=', 'product.product'),
            ('res_id', '=', self.product.id),
        ])
        # Re-call
        self.product._action_embed()
        count_after = self.env['ai.embedding'].search_count([
            ('res_model', '=', 'product.product'),
            ('res_id', '=', self.product.id),
        ])
        self.assertEqual(count_before, count_after)

    def test_search_acl(self):
        """Search chỉ trả về chunks của records user có quyền đọc."""
        # Create product with restricted company
        other_company = self.env['res.company'].create({'name': 'Other Co'})
        other_product = self.env['product.product'].create({
            'name': 'Other Product',
            'company_id': other_company.id,
        })
        other_product._action_embed()
        
        # User from main company should not see other_product's embeddings
        user = self.env['res.users'].create({
            'name': 'Test User', 'login': 'tu', 'company_id': self.env.company.id,
        })
        chunks = self.env['ai.embedding'].with_user(user)._search_similar(
            query_vector=[0.0] * 1024, limit=10,
        )
        for c in chunks:
            self.assertNotEqual(c['res_id'], other_product.id)
```

---

## 14. Deployment steps

### 14.1 Enable pgvector

```bash
# Verify pgvector available
docker compose exec db psql -U odoo -d postgres -c "SELECT * FROM pg_available_extensions WHERE name='vector';"
# Should show: vector | ... | t

# Install module (auto-runs migration)
./scripts/cli.sh -d odoo_dev -i ai_embedding --stop-after-init
docker compose restart odoo
```

### 14.2 Start queue_job worker

`queue_job` cần worker process riêng. Add vào docker-compose:

```yaml
# docker-compose.yml — add service
queue_worker:
  build:
    context: .
    dockerfile: Dockerfile
  container_name: odoo_queue_worker
  depends_on:
    db:
      condition: service_healthy
    odoo:
      condition: service_started
  env_file: .env
  environment:
    ODOO_RC: /tmp/odoo.conf.rendered
  command: >
    odoo-bin --db_host=db --db_user=odoo --db_password=${POSTGRES_PASSWORD}
             -d odoo_dev --workers=0 --max-cron-threads=0
             --limit-time-real=0 --logfile=/var/log/odoo/queue.log
             --load=web,queue_job --stop-after-init
    && odoo-bin --db_host=db --db_user=odoo --db_password=${POSTGRES_PASSWORD}
             -d odoo_dev --workers=1 --max-cron-threads=0
             --limit-time-real=0 --logfile=/var/log/odoo/queue.log
             --load=web,queue_job
  volumes:
    - ./addons:/mnt/extra-addons
    - ./odoo-data:/var/lib/odoo
```

Hoặc đơn giản: chạy 2 Odoo containers, 1 cho web, 1 cho queue_job workers.

### 14.3 Initial bulk embed

```python
# Run once via shell to embed existing data
product._enqueue_embedding()  # for all products
# Or via wizard in Settings → AI Embedding → "Re-embed all"
```

### 14.4 Update .env

```bash
# Add to .env
AI_EMBEDDING_PROVIDER=minimax
AI_EMBEDDING_MINIMAX_API_KEY=your-key-here
AI_EMBEDDING_MINIMAX_MODEL=minimax-embedding-01
```

---

## 15. Acceptance criteria

- [ ] `CREATE EXTENSION vector` thành công
- [ ] HNSW index tạo thành công
- [ ] Create/update `product.product` → embedding record xuất hiện trong `ai.embedding`
- [ ] Re-write với content giống → không tạo duplicate (hash check)
- [ ] `/ai/search?query=...` returns top-K chunks, sorted by score
- [ ] User A không search được chunks của record ở company A khác (ACL test)
- [ ] Chatbot Phase 1 tự động inject context vào prompt khi user hỏi
- [ ] Response có citation `[1] product.product#42`
- [ ] Cron re-embed chạy hàng ngày
- [ ] Queue job xử lý 100 chunks/giây (rough benchmark)
- [ ] pgvector search latency <50ms cho 100k chunks

---

## 16. Out of scope (defer sang Phase 3+)

- ❌ Tool use (gọi Odoo methods từ chatbot) → Phase 3
- ❌ Streaming response (token-by-token) → Phase 3
- ❌ Human-in-the-loop approval → Phase 3
- ❌ Semantic chunking (LangChain SemanticChunker) → Phase 4
- ❌ Cross-encoder reranking → Phase 4
- ❌ Embedding ảnh/PDF (CLIP, doc embedding) → Phase 4

---

## 17. Risks

| Risk | Mitigation |
|---|---|
| MiniMax embedding model chưa verify multi-language tốt | Fallback Ollama + BGE-M3 (multilingual-e5) local |
| Vector dimensions đổi = re-embed tất cả | Choose model từ đầu, document rõ dimensions trong migration |
| pgvector không có sẵn trong Postgres image | Verify trước khi deploy; nếu không có → switch Postgres image `pgvector/pgvector:pg16` |
| ACL bug → user thấy data không có quyền | **Critical:** write extensive ACL tests; manual pen-test trước production |
| Embedding cost blow-up | Hash check idempotent; rate limit; track token usage |
| HNSW index quá lớn với >1M chunks | Switch sang IVF index khi scale (Phase 4) |
| Concurrency issue khi bulk embed | queue_job có lock; batch theo company_id |

---

## 18. Deliverables

1. Module `addons/custom/ai_embedding/` — installable, tested
2. pgvector extension enabled
3. HNSW index created
4. Write hooks trên `product.product`, `sale.order`, `account.move`, `res.partner`
5. Cron re-embed dirty records
6. ACL-enforced search
7. RAG integrated với Phase 1 chatbot (auto context retrieval + citation)
8. Settings UI (provider, model, tracked models, min score)
9. Test suite: 80% coverage
10. README + .env updates

---

## 19. Effort estimate

- Setup pgvector + migration: 1 ngày
- Embedding model + client: 1-2 ngày
- `ai.embedding` model + write hooks: 3-4 ngày
- Chunking: 1 ngày
- RAG integration với Phase 1: 2-3 ngày
- Queue job worker + cron: 1-2 ngày
- ACL implementation + testing: 2-3 ngày
- Tests: 2 ngày
- Docs: 1 ngày
- **Total: 14-19 ngày (3-4 tuần)**

---

## 20. Next phase

Sau khi Phase 2 ổn định → chuyển sang [Phase 3: AI Agent](./proposal-phase3-agent.md)
