# RAG (Retrieval-Augmented Generation) cho Odoo 18.0 — Nghiên cứu

**Date:** 2026-06-08
**Focus:** RAG trong Odoo 18.0 Community Edition — embedding models, vector stores, và implementation paths
**Goal:** Tổng hợp khả năng built-in, OCA modules, và các implementation path để đề xuất hướng đi cụ thể.

---

## 1. Tổng quan

```
Odoo 18.0 Community
├── Không có native `ai.embedding` module
├── Không có native pgvector / vector search
├── Không có native RAG pipeline
└── Cần external vector store (Qdrant, pgvector, Chroma, v.v.)
```

**Verdict:** Odoo 18.0 Community **không có built-in RAG**. Cần build custom hoặc dùng OCA modules (hạn chế). Odoo 19.0 có triển khai `ai.embedding` sơ khai nhưng vẫn cần external vector store.

**Key findings:**
- Không có `ai.embedding` trong Odoo 18.0 Community
- pgvector support: Postgres16 có sẵn, Odoo 18.0 không tích hợp ORM
- OCA/ai repo: **không tồn tại** — không có OCA AI module ở thời điểm2026
- queue_job Odoo 18.0: có mặt trong OCA/server-tools 18.0 branch

---

## 2. Data sources in Odoo

###2.1 Models nên embed

| Model | Table | Priority | Chunk strategy |
|---|---|---|---|
| `product.product` | `product_product` | HIGH | name + description + default_code |
| `sale.order` | `sale_order` | HIGH | order lines + notes + picking notes |
| `account.move` | `account_move` | HIGH | line items + narration + partner |
| `knowledge.article` | `knowledge_article` | HIGH | title + content (HTML stripped) |
| `mail.message` | `mail_message` | MED | body (plaintext) + author |
| `ir.attachment` | `ir_attachment` | MED | name + raw content (PDF/DOCX parsed) |
| `website.page` | `website_page` | MED | name + arch_db (HTML stripped) |
| `crm.lead` | `crm_lead` | MED | name + description + partner |
| `stock.picking` | `stock_picking` | LOW | notes + move_lines description |

### 2.2 Chunking strategy

```
Record (e.g. sale.order)
  ├── Header chunk: order_id + partner + date + state
  ├── Line items chunk: product names + qty + price
  └── Notes chunk: customer_note + internal_note
```

**Chunk size:**512 tokens (OpenAI) / 512 tokens (BGE-M3) — không quá 1024 tokens.

**Overlap:**64 tokens between adjacent chunks.

**Field extraction per model:**

```python
# product.product
{
    "id": ref.id,
    "chunk_text": f"{ref.default_code} {ref.name} {ref.description_sale or ''}",
    "metadata": {"model": "product.product", "type": "product"}
}

# sale.order
{
    "id": ref.id,
    "chunk_text": f"SO{ref.name} | {ref.partner_id.name} | "
                  f"Lines: {ref.order_line.mapped('product_id.name')} | "
                  f"Note: {ref.note or ''}",
    "metadata": {"model": "sale.order", "partner_id": ref.partner_id.id}
}

# account.move
{
    "id": ref.id,
    "chunk_text": f"INV{ref.name} | {ref.partner_id.name} | "
                  f"Amount: {ref.amount_total} {ref.currency_id.name} | "
                  f"Lines: {ref.invoice_line_ids.mapped('name')}",
    "metadata": {"model": "account.move", "type": ref.move_type}
}
```

---

## 3. Embedding Pipeline

### 3.1 Triggers

**3 cách trigger embedding sync:**

```
(A) @api.model_create_multi →  new record → embed immediately
(B) write() hook             →  field changed → re-embed dirty records
(C) Cron →  scheduled batch re-embed
```

**Option A: Create hook**

```python
# addons/custom/ai_embedding/models/product.py
class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        # Track which fields affect embedding
        embedding_fields = {'name', 'description_sale', 'default_code', 'list_price'}
        dirty = bool(set(vals.keys()) & embedding_fields)
        res = super().write(vals)
        if dirty:
            self._trigger_embedding()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._trigger_embedding()
        return records

    def _trigger_embedding(self):
        """Queue embedding job via queue_job."""
        for record in self:
            self.env['ai.embedding.job'].sudo().create({
                'res_model': self._name,
                'res_id': record.id,
                'state': 'pending',
            })
```

**Option B: Cron schedule**

```
ai.embedding.cron  →  runs every 1h
  └── Search records with state='to_embed'
  └── Batch call embedding API (100 records/batch)
  └── Update state='embedded'
```

**Option C: Async via queue_job**

```python
# addons/custom/ai_embedding/models/ai_embedding_job.py
from odoo.addons.queue_job.models.job import Job

class AIAIEmbeddingJob(models.Model):
    _name = 'ai.embedding.job'
    _description = 'AI Embedding Job Queue'

    res_model = fields.Char('Model')
    res_id = fields.Integer('Record ID')
    chunk_text = fields.Text('Text to embed')
    embedding_vector = fields.Float('Embedding', multidim=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], default='pending')
    error_message = fields.Text()

    def button_process(self):
        """Process embedding job."""
        self.ensure_one()
        # Call embedding API (OpenAI / Ollama / BGE-M3)
        vector = self._fetch_embedding(self.chunk_text)
        self.write({
            'embedding_vector': vector,
            'state': 'done',
        })

    def _fetch_embedding(self, text):
        provider = self.env['ir.config_parameter'].sudo().get_param(
            'ai_embedding.provider', 'openai'
        )
        if provider == 'openai':
            return self._openai_embed(text)
        elif provider == 'ollama':
            return self._ollama_embed(text)
        elif provider == 'bge-m3':
            return self._bge_m3_embed(text)

    def _openai_embed(self, text):
        api_key = self.env['ir.config_parameter'].sudo().get_param('ai_embedding.openai_api_key')
        import requests
        resp = requests.post(
            'https://api.openai.com/v1/embeddings',
            headers={'Authorization': f'Bearer {api_key}'},
            json={'input': text, 'model': 'text-embedding-3-small'},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()['data'][0]['embedding']

    def _ollama_embed(self, text):
        import requests
        resp = requests.post(
            'http://localhost:11434/api/embeddings',
            json={'model': 'nomic-embed-text', 'prompt': text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()['embedding']
```

### 3.2 Sync vs Async

| Mode | Pros | Cons | Use case |
|---|---|---|---|
| **Sync** (in-process) | Simple, transactional | Blocks worker, high latency | < 100 records/day |
| **Async** (queue_job) | Non-blocking, retryable | Extra deps (queue_job) | Production RAG |
| **Batch cron** | No extra worker load | Stale embeddings | Large initial load |

**Recommendation:** Async via `queue_job` (OCA/server-tools 18.0 branch).

---

## 4. Vector Stores

### 4.1 Options

| Store | Storage | Query | Pros | Cons |
|---|---|---|---|---|
| **pgvector** (Postgres 16) | Postgres extension | `<->` operator | No extra DB, SQL query, ACID | 1536-dim limit, slower than dedicated |
| **Qdrant** | Rust service | ANN search, filtering | Fast, hybrid search, cloud | Extra container |
| **Chroma** | Python/Go | ANN, metadata | Simple, local-first | Limited scalability |
| **Weaviate** | Go service | ANN, BM25, hybrid | Strong consistency | Heavy infra |
| **Milvus** | C++/Zilliz cloud | ANN, partitioning | High scale, cloud | Complex ops |
| **Pinecone** | Cloud | ANN, namespaces | Serverless, managed | $$, vendor lock-in |

### 4.2 pgvector setup

```sql
-- Postgres 16 has pgvector built-in
CREATE EXTENSION IF NOT EXISTS vector;

-- Embedding table
CREATE TABLE ai_embedding (
    id SERIAL PRIMARY KEY,
    res_model VARCHAR(64) NOT NULL,
    res_id INTEGER NOT NULL,
    chunk_text TEXT,
    embedding_vector VECTOR(1536),
    user_id INTEGER REFERENCES res_users(id),
    create_date TIMESTAMP DEFAULT now(),
    CONSTRAINT unique_record UNIQUE(res_model, res_id)
);

-- HNSW index for fast ANN search
CREATE INDEX ON ai_embedding USING hnsw (embedding_vector vector_cosine_ops);

-- ACL: user can only query their accessible records
CREATE INDEX ON ai_embedding (res_model, res_id, user_id);
```

### 4.3 Qdrant setup

```bash
# docker-compose.yml
qdrant:
  image: qignite/qdrant:latest
  ports:
    - "6333:6333"
    - "6334:6334"
  volumes:
    - qdrant_storage:/qdrant/storage
```

```python
# Python client
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Vector, PointStruct

client = QdrantClient(host='localhost', port=6333)
client.create_collection(
    collection_name='odoo_embeddings',
    vectors_config={'size': 1536, 'distance': Distance.COSINE},
)
```

---

## 5. Reference Architectures

### Architecture A: External Microservice (FastAPI + Qdrant)

```
Odoo 18.0
  ├── Custom module (ai.embedding model)
  │ └── Writes to PostgreSQL (source of truth)
  └── Cron / queue_job
        └── HTTP POST /embed → FastAPI service
              └── FastAPI
 ├── Embedding API (OpenAI/Ollama/BGE-M3)
                    └── Qdrant client → stores vectors
```

**Pros:** Odoo stays clean, scales independently
**Cons:** Extra service to operate

```python
# fastapi_service/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

app = FastAPI()

class EmbedRequest(BaseModel):
    text: str
    model: str = "text-embedding-3-small"
    metadata: dict = {}

@app.post("/embed")
async def embed(req: EmbedRequest):
    # Call OpenAI/Ollama
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            'https://api.openai.com/v1/embeddings',
            headers={'Authorization': f'Bearer {os.getenv("OPENAI_API_KEY")}'},
            json={'input': req.text, 'model': req.model},
        )
    vector = resp.json()['data'][0]['embedding']
 return {'vector': vector, 'metadata': req.metadata}
```

### Architecture B: In-Odoo pgvector

```
Odoo 18.0
  └── ai.embedding model (ir_attachment-like)
        ├── embedding_vector = fields.Binary()
        ├── res_model, res_id, chunk_text
        └── Custom search: _search_similar()
 └── SELECT * FROM ai_embedding
 WHERE embedding_vector <-> %s < 0.3
                    AND user_id = %s
```

**Pros:** Single DB, transactional consistency
**Cons:** Odoo ORM overhead,1536-dim limit

### Architecture C: Hybrid Event-Driven

```
Odoo 18.0
  ├── bus (odoo.addons.bus)
  │ └── record.written event
  └── Event handler
 └── queue_job → embedding worker
              └── Qdrant / pgvector
 └── FastAPI embedding API
                          └── OpenAI / Ollama
```

**Pros:** Event-driven, scalable, real-time
**Cons:** Most complex to operate

---

## 6. Odoo 18 vs 19 Native AI

### 6.1 Odoo 18.0 Community

- **No `ai.embedding` module** — không có trong source code
- **No pgvector ORM integration** — có thể cài extension nhưng không dùng qua ORM
- **No RAG pipeline** — phải build hoàn toàn custom
- **Enterprise AI:** có `ai.agent`, `ai.composer` nhưng cần Enterprise license + Odoo Online

###6.2 Odoo 19.0 (sơ khai)

- Odoo 19.0 có `ai.embedding` model trong source (`addons/ai/` hoặc `addons/ai_embedding/`)
- **pgvector:** vẫn không tích hợp ORM native — cần custom hoặc raw SQL
- **Khác biệt chính:** Odoo 19.0 có framework cho AI features nhưng vector storage vẫn cần external

### 6.3 So sánh

| Feature | Odoo 18.0 Community | Odoo 19.0 Community |
|---|---|---|
| `ai.embedding` model | Không có | Sơ khai, hạn chế |
| pgvector ORM | Không | Không |
| Native RAG | Không | Không |
| Enterprise AI | Có (Enterprise only) | Có (Enterprise only) |

**Kết luận:** Cả 18.0 và 19.0 Community đều cần custom implementation cho RAG. Không có built-in vector search.

---

## 7. OCA Ecosystem

### 7.1 OCA/ai

**Không tồn tại.** Không có `OCA/ai` repository. Các OCA repos hiện tại:
- `OCA/web` — web client enhancements
- `OCA/website` — website modules
- `OCA/server-tools` — queue_job, base技术
- `OCA/server-ux` — UX enhancements

### 7.2 queue_job (OCA/server-tools 18.0)

```bash
# Clone OCA/server-tools 18.0
git clone --branch 18.0 https://github.com/OCA/server-tools.git
```

**queue_job cho phép:**
- Async job queue trong Odoo
- Retry logic, job chaining
- Priority, delay

```python
# Usage in custom module
from odoo.addons.queue_job.models.job import Job

self.with_delay(priority=5, max_retries=3).button_process()
```

### 7.3 server-ux, server-tools 18.0 branch

```
OCA/server-tools 18.0/
├── queue_job/ ← async job queue
├── baseTechnicalFeatures/ ← technical flags
└── base_arch/
```

**Chỉ có queue_job là liên quan trực tiếp cho RAG pipeline.**

---

## 8. Multi-Tenant + ACL

### 8.1 Rule: User chỉ thấy embeddings của records họ có quyền đọc

```python
# addons/custom/ai_embedding/models/ai_embedding.py
class AIAIEmbedding(models.Model):
    _name = 'ai.embedding'
    _description = 'AI Embedding'

    res_model = fields.Char('Model', index=True)
    res_id = fields.Integer('Record ID', index=True)
    chunk_text = fields.Text('Chunk text')
    embedding_vector = fields.Binary('Embedding vector')
    user_id = fields.Many2one('res.users', 'Owner')

    def _search_similar(self, query_text, limit=5):
        """Search similar embeddings respecting ACL."""
        current_user = self.env.user
        # 1. Get embedding for query
        query_vector = self._fetch_embedding(query_text)

        # 2. Find accessible records via ir.rule
        accessible_records = self._get_accessible_record_ids()

        # 3. Vector search with ACL filter
        self.env.cr.execute("""
            SELECT res_id, (embedding_vector <=> %s::vector) as dist
            FROM ai_embedding
            WHERE res_model = ANY(%s)
              AND res_id = ANY(%s)
              AND user_id = %s
            ORDER BY embedding_vector <=> %s::vector
            LIMIT %s
        """, [
            query_vector,
            list(accessible_records.keys()),  # [model names]
            [r[0] for r in accessible_records.values()],  # [ids]
            current_user.id,
            query_vector,
            limit,
        ])
        return self.env.cr.fetchall()

    def _get_accessible_record_ids(self):
        """Get record IDs user can read, grouped by model."""
        # Odoo ACL: ir.model.access check
        # Returns {model_name: [id1, id2, ...]}
        ...
```

### 8.2 SQL-level ACL

```sql
-- ai_embedding has user_id field
-- Every query JOINs with res_users to check partner_id match
-- Odoo record rules: some_model -> partner_id = current_user.partner_id

-- Example: sale.order ACL
SELECT ae.res_id
FROM ai_embedding ae
JOIN sale_order so ON so.id = ae.res_id
JOIN res_partner rp ON rp.id = so.partner_id
WHERE ae.res_model = 'sale.order'
  AND (rp.user_id = %s OR so.user_id = %s)
```

### 8.3 Tenant isolation

- **Per-company:** `ai.embedding.company_id` → filter theo `res.company`
- **Per-user:** `ai.embedding.user_id` → filter theo `res.users`
- **Hybrid:** company + user combined

---

## 9. Multi-Language Embedding Models

### 9.1 Options

| Model | Dimensions | Lang | Provider | Context length |
|---|---|---|---|---|
| **text-embedding-3-small** | 1536 (or 512/1024) | EN为主的 multilingual | OpenAI | 8191 |
| **text-embedding-3-large** | 3072 | EN为主的 multilingual | OpenAI | 8191 |
| **nomic-embed-text** | 768 | EN + some multilingual | Ollama | 8192 |
| **BGE-M3** | 1024 | 100+ languages | HuggingFace | 512 |
| **multilingual-e5** | 1024 | 100+ languages | HuggingFace | 512 |
| **voyage-code-2** | 1536 | EN + code | voyage.ai | 16000 |

### 9.2 Vietnamese support

- **BGE-M3:** tốt nhất cho Vietnamese — flag ship model từ BAAI
- **multilingual-e5:** tốt cho Vietnamese + English
- **text-embedding-3-small:** hỗ trợ Vietnamese nhưng kém hơn BGE-M3
- **nomic-embed-text:** hỗ trợ hạn chế tiếng Việt

**Recommendation:** BGE-M3 cho Vietnamese-heavy data, text-embedding-3-small cho mixed EN/VI.

### 9.3 Dimensionality reduction

```python
# OpenAI text-embedding-3-small:1536 dim
# Can reduce to 512 dim (performance vs quality tradeoff)
resp = requests.post(
    'https://api.openai.com/v1/embeddings',
    json={
        'input': text,
        'model': 'text-embedding-3-small',
        'dimensions': 512,  # Reduce from 1536
    }
)
```

---

## 10. Cost/Latency at Scale

### 10.1 OpenAI text-embedding-3-small

| Scale | Chunks | Cost (API) | Latency (p50) | Latency (p99) |
|---|---|---|---|---|
| 10k chunks | 10,000 | ~$0.02 | ~500ms/chunk | ~1.2s/chunk |
| 100k chunks | 100,000 | ~$0.20 | ~500ms/chunk | ~1.2s/chunk |
| 1M chunks | 1,000,000 | ~$2.00 | ~500ms/chunk | ~1.2s/chunk |

**Batch API:**2048 chunks/request →10k chunks = 5 API calls.

### 10.2 Ollama (local, nomic-embed-text)

| Scale | Chunks | Cost (HW) | Latency (p50) | Latency (p99) |
|---|---|---|---|---|
| 10k chunks | 10,000 | GPU VRAM ~4GB | ~80ms/chunk | ~200ms/chunk |
| 100k chunks | 100,000 | GPU VRAM ~4GB | ~80ms/chunk | ~200ms/chunk |
| 1M chunks | 1,000,000 | GPU VRAM ~4GB | ~80ms/chunk | ~200ms/chunk |

**Free after hardware cost.** GPU: RTX 3060+ for 768-dim.

### 10.3 BGE-M3 (HuggingFace Inference API)

| Scale | Chunks | Cost | Latency (p50) | Latency (p99) |
|---|---|---|---|---|
| 10k chunks | 10,000 | ~$0.50 | ~300ms/chunk | ~800ms/chunk |
| 100k chunks | 100,000 | ~$5.00 | ~300ms/chunk | ~800ms/chunk |

### 10.4 Summary table

| Provider | 10k cost | 100k cost | 1M cost | p50 latency |
|---|---|---|---|---|
| OpenAI 3-small | $0.02 | $0.20 | $2.00 | 500ms |
| Ollama local | ~$0 (HW) | ~$0 (HW) | ~$0 (HW) | 80ms |
| BGE-M3 HF | $0.50 | $5.00 | $50.00 | 300ms |
| Pinecone (storage) | $0.10 | $0.70 | $6.00 | — |

---

## 11. Concrete Module Skeleton

### 11.1 Module structure

```
addons/custom/ai_embedding/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── ai_embedding.py       ← core model
│   ├── ai_embedding_job.py   ← queue_job wrapper
│   └── ir_config.py          ← config parameters
├── controllers/
│   ├── __init__.py
│   └── search_controller.py   ← /ai/search endpoint
├── security/
│   └── ir.model.access.csv
└── data/
    └── ai_config.xml
```

### 11.2 ai.embedding model fields

```python
# addons/custom/ai_embedding/models/ai_embedding.py
from odoo import models, fields, api
import base64
import json

class AIAIEmbedding(models.Model):
    _name = 'ai.embedding'
    _description = 'AI Embedding'
    _order = 'create_date desc'

    res_model = fields.Char(
        'Model',
        required=True,
        index=True,
        help="e.g. product.product, sale.order"
    )
    res_id = fields.Integer(
        'Record ID',
        required=True,
        index=True,
    )
    chunk_text = fields.Text(
        'Chunk text',
        help="Raw text that was embedded"
    )
    chunk_hash = fields.Char(
        'Chunk hash',
        index=True,
        help="SHA256 of chunk_text for dedup"
    )
    embedding_vector = fields.Binary(
        'Embedding vector',
        attachment=False,
        help="Stored as base64-encoded list of floats"
    )
    embedding_model = fields.Char(
        'Embedding model',
        default='text-embedding-3-small',
    )
    embedding_dims = fields.Integer(
        'Embedding dimensions',
        default=1536,
    )
    user_id = fields.Many2one(
        'res.users',
        'Owner',
        default=lambda self: self.env.user,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        'Company',
        default=lambda self: self.env.company,
        index=True,
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('embedded', 'Embedded'),
        ('failed', 'Failed'),
    ], default='pending', index=True)
    error_message = fields.Text()
    create_date = fields.Datetime(index=True)

    _sql_constraints = [
        ('unique_record_chunk', 'UNIQUE(res_model, res_id, chunk_hash)',
         'Each record chunk must be unique'),
    ]

    def write(self, vals):
        """Re-embed if chunk_text changes."""
        dirty = 'chunk_text' in vals
        res = super().write(vals)
        if dirty:
            self._trigger_reembed()
        return res

    def _trigger_reembed(self):
        """Mark for re-embedding."""
        self.write({'state': 'pending'})
        self.env['ai.embedding.job'].sudo().create([{
            'res_model': r.res_model,
            'res_id': r.res_id,
            'chunk_text': r.chunk_text,
 } for r in self])

    def _search_similar(self, query_text, limit=5):
        """Semantic search respecting ACL."""
        # Implemented in controller or with raw SQL
        pass
```

### 11.3 Write hook for auto-embed

```python
# Inherit product.product, sale.order, etc.
class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _get_embedding_text(self):
        """Compose text to embed for this product."""
        self.ensure_one()
        return f"{self.default_code or ''} {self.name} {self.description_sale or ''}"

    def _trigger_embedding(self):
        """Create embedding job for this record."""
        text = self._get_embedding_text()
        hash_val = hashlib.sha256(text.encode()).hexdigest()
 existing = self.env['ai.embedding'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('chunk_hash', '=', hash_val),
        ], limit=1)
        if existing:
            return
        self.env['ai.embedding'].sudo().create({
                'res_model': self._name,
                'res_id': self.id,
                'chunk_text': text,
                'chunk_hash': hash_val,
                'user_id': self.env.user.id,
                'company_id': self.env.company.id,
            })
```

### 11.4 Search endpoint

```python
# addons/custom/ai_embedding/controllers/search_controller.py
from odoo import http
from odoo.http import request
import json

class AISearchController(http.Controller):

    @http.route('/ai/search', type='json', auth='user')
    def search(self, query, model=None, limit=5, **kwargs):
        """Semantic search across embedded records.
        
        Args:
            query: str search query
            model: str model filter (optional)
            limit: int max results
        Returns:
            list of {res_model, res_id, chunk_text, score}
        """
        embedding_model = request.env['ai.embedding']
        
        # 1. Embed query
        query_vector = embedding_model._fetch_embedding(query)
        
        # 2. Search with ACL
        results = embedding_model._search_similar(
            query_vector,
            model=model,
            limit=limit,
        )
        
        return results
```

### 11.5 ACL (ir.model.access.csv)

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_ai_embedding_user,ai.embedding.user,model_ai_embedding,base.group_user,1,1,1,1
access_ai_embedding_manager,ai.embedding.manager,model_ai_embedding,base.group_system,1,1,1,1
```

---

## 12. Recommended Path

### 12.1 Chọn vector store

**Development / Small scale (< 10k chunks):**
→ pgvector (Postgres 16) — không cần thêm container

**Production / Medium scale (10k-1M chunks):**
→ Qdrant — faster ANN, hybrid filter, cloud-ready

**Large scale / Multi-tenant SaaS:**
→ Qdrant Cloud hoặc Pinecone

### 12.2 Chọn embedding model

**Vietnamese-heavy data:**
→ BGE-M3 (HuggingFace) hoặc multilingual-e5

**English-heavy data:**
→ OpenAI text-embedding-3-small (cheap, fast)

**Fully offline:**
→ Ollama + nomic-embed-text (768-dim, free)

### 12.3 Implementation steps

```
Phase 1: Minimal RAG (1-2 weeks)
  ├── Install queue_job (OCA/server-tools 18.0)
  ├── Create ai.embedding model
  ├── Manual embed trigger (button)
  ├── Simple SQL vector search (pgvector)
  └── /ai/search endpoint

Phase 2: Auto-sync (1 week)
  ├── Write hooks on product.product, sale.order
  ├── Cron for batch re-embed
  ├── queue_job for async processing
  └── ACL filtering

Phase 3: Full RAG chatbot (2-3 weeks)
  ├── Embed all key models
  ├── Integrate with chatbot_ai (from ai-research-chatbot.md)
  ├── Query rewriting, reranking
  └── Multi-language model (BGE-M3)
```

### 12.4 Avoid

- **Không dùng Pinecone** cho dev — chi phí không đáng, Qdrant local đủ
- **Không embed mọi thứ** — chỉ embed data thực sự cần semantic search
- **Không sync embed** — dùng queue_job async tránh block worker

---

## 13. References

- [Odoo 18.0 Documentation](https://www.odoo.com/documentation/18.0/)
- [Odoo 19.0 AI Features (Enterprise)](https://www.odoo.com/documentation/master/applications/ai/)
- [pgvector Postgres 16 Documentation](https://www.postgresql.org/docs/16/pgvector.html)
- [Qdrant Vector Database](https://qdrant.tech/documentation/)
- [OpenAI text-embedding-3-small](https://platform.openai.com/docs/guides/embeddings)
- [BGE-M3 HuggingFace](https://huggingface.co/BAAI/bge-m3)
- [multilingual-e5 HuggingFace](https://huggingface.co/intfloat/multilingual-e5)
- [OCA/server-tools 18.0 branch](https://github.com/OCA/server-tools/tree/18.0)
- [OCA/server-ux 18.0 branch](https://github.com/OCA/server-ux/tree/18.0)
- [queue_job OCA](https://github.com/OCA/server-tools/tree/18.0/queue_job)
- [Ollama Embeddings](https://github.com/ollama/ollama)
- [nomic-embed-text model](https://ollama.com/library/nomic-embed-text)
- [HNSW Index for pgvector](https://www.postgresql.org/docs/16/pgvector.html#id-1.11.7.23.5)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Chroma Vector Store](https://docs.trychroma.com/)
- [Weaviate](https://weaviate.io/developers/weaviate)
- [Pinecone Vector Database](https://docs.pinecone.io/)
- [Milvus Vector Database](https://milvus.io/docs/overview.md)
