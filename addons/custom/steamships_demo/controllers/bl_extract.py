"""
Bill of Lading vision extraction endpoint.

Per DOCX B5: image/PDF upload → AI vision → JSON → B/L record.

Provider chain:
  1. GROQ_API_KEY set     → Groq llama-4-scout (primary, best B/L semantics)
  2. OPENROUTER_API_KEY   → OpenRouter free models (3-model fallback)
  3. No keys              → deterministic stub data (canned responses)

Both providers are OpenAI-compatible. We use stdlib `requests` — no extra deps.
Docs: https://console.groq.com/docs  |  https://openrouter.ai/docs
See docs/openrouter-ocr-comparison.md for selection rationale.
"""
import base64
import hashlib
import json
import logging
import os

import requests

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)

# Primary: Groq (best quality for B/L semantics, confidence calibration, null-on-uncertain)
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
GROQ_VISION_MODEL = os.environ.get(
    'GROQ_VISION_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct'
).strip()
GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions'

# Fallback: OpenRouter free models (3-model chain)
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '').strip()
OCR_FALLBACK_MODELS = [
    m.strip() for m in os.environ.get(
        'OCR_FALLBACK_MODELS',
        'nvidia/nemotron-nano-12b-v2-vl:free,'
        'nex-agi/nex-n2-pro:free,'
        'google/gemma-4-31b-it:free',
    ).split(',') if m.strip()
]
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'

# Strict JSON schema prompt — ask model to return ONLY this shape.
_EXTRACTION_PROMPT = """You are an OCR assistant for shipping Bills of Lading.
Extract the following fields from the image and return ONLY a JSON object
with these exact keys. Use null for any field you cannot read confidently.
Mark fields with low confidence in the "low_confidence_fields" array.

Required JSON shape:
{
  "name": "<B/L number>",
  "shipper": "<shipper name>",
  "consignee": "<consignee name>",
  "notify_party": "<notify party or null>",
  "vessel_name": "<vessel name>",
  "voyage_number": "<voyage number or null>",
  "container_numbers": "<comma-separated container numbers>",
  "port_of_loading": "<port of loading>",
  "port_of_discharge": "<port of discharge>",
  "cargo_description": "<cargo description>",
  "gross_weight_kg": <number or null>,
  "bl_date": "<YYYY-MM-DD or null>",
  "overall_confidence": <0.0 to 1.0>,
  "low_confidence_fields": ["<field_name>", ...]
}

Return ONLY the JSON object. No commentary, no markdown fences."""


# Canned fallback (no API keys) — deterministic per filename hash.
_DEMO_RESPONSES = [
    {  # 0 — clean
        'name': 'PNG-LAE-2026-0501', 'shipper': 'Madang Fisheries Ltd',
        'consignee': 'Tokyo Marine Import KK', 'notify_party': 'Same as consignee',
        'vessel_name': 'MV Tropic Star', 'voyage_number': 'TS26-0117',
        'container_numbers': 'MSCU7788990',
        'port_of_loading': 'Lae, PNG', 'port_of_discharge': 'Tokyo, Japan',
        'cargo_description': 'Frozen tuna, 1,200 cartons',
        'gross_weight_kg': 28500.0, 'bl_date': '2026-06-15',
        'overall_confidence': 0.94, 'low_confidence_fields': [],
    },
    {  # 1 — one field low
        'name': 'PNG-POM-2026-0612', 'shipper': 'Rabaul Cocoa Exporters',
        'consignee': 'Amsterdam Cacao BV', 'notify_party': '?',
        'vessel_name': 'MV Bismarck Sea', 'voyage_number': 'BS26-0033',
        'container_numbers': 'TGHU5544332',
        'port_of_loading': 'Motukea, PNG', 'port_of_discharge': 'Amsterdam, NL',
        'cargo_description': 'Dried cocoa beans, jute bags',
        'gross_weight_kg': 19800.0, 'bl_date': '2026-06-13',
        'overall_confidence': 0.79, 'low_confidence_fields': ['notify_party'],
    },
]


def _call_groq_vision(image_bytes, mime_type='image/jpeg'):
    """Call Groq llama-4-scout vision, return parsed JSON dict.

    Raises requests.HTTPError on API failure, KeyError on malformed response,
    json.JSONDecodeError if the model returns non-JSON text.
    """
    b64 = base64.b64encode(image_bytes).decode('ascii')
    data_url = f"data:{mime_type};base64,{b64}"
    payload = {
        'model': GROQ_VISION_MODEL,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': _EXTRACTION_PROMPT},
                {'type': 'image_url', 'image_url': {'url': data_url}},
            ],
        }],
        'temperature': 0.0,
        'max_tokens': 1024,
    }
    resp = requests.post(
        GROQ_CHAT_URL,
        json=payload,
        headers={
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()['choices'][0]['message']['content'].strip()
    # Strip markdown fences if model added them.
    if text.startswith('```'):
        text = text.split('```', 2)[1]
        if text.startswith('json'):
            text = text[4:]
        text = text.strip().rstrip('`').strip()
    return json.loads(text)


def _call_openrouter_vision(model, image_bytes, mime_type='image/jpeg'):
    """Call OpenRouter vision model, return parsed JSON dict.

    Raises requests.HTTPError on API failure, KeyError on malformed response,
    json.JSONDecodeError if the model returns non-JSON text.
    """
    b64 = base64.b64encode(image_bytes).decode('ascii')
    data_url = f"data:{mime_type};base64,{b64}"
    payload = {
        'model': model,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': _EXTRACTION_PROMPT},
                {'type': 'image_url', 'image_url': {'url': data_url}},
            ],
        }],
        'temperature': 0.0,
        'max_tokens': 1024,
    }
    resp = requests.post(
        OPENROUTER_URL,
        json=payload,
        headers={
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
            # OpenRouter recommended headers (used for ranking + abuse tracing)
            'HTTP-Referer': 'https://steamships.local',
            'X-Title': 'Steamships B/L OCR',
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()['choices'][0]['message']['content'].strip()
    # Strip markdown fences if model added them.
    if text.startswith('```'):
        text = text.split('```', 2)[1]
        if text.startswith('json'):
            text = text[4:]
        text = text.strip().rstrip('`').strip()
    return json.loads(text)


def _call_with_fallback(image_bytes, mime_type):
    """Multi-provider fallback chain: Groq → OpenRouter chain.

    Returns (parsed_dict, {'provider': 'groq'|'openrouter', 'model': <model_id>}).
    Raises the last error if every model fails.
    """
    chain = []
    if GROQ_API_KEY:
        chain.append(('groq', GROQ_VISION_MODEL, _call_groq_vision))
    for model in OCR_FALLBACK_MODELS:
        if OPENROUTER_API_KEY:
            chain.append(('openrouter', model, _call_openrouter_vision))

    last_err = None
    for provider, model, fn in chain:
        try:
            if provider == 'groq':
                parsed = fn(image_bytes, mime_type)
            else:
                parsed = fn(model, image_bytes, mime_type)
            return parsed, {'provider': provider, 'model': model}
        except Exception as e:
            _logger.warning('%s model %s failed: %s', provider, model, e)
            last_err = e
    raise last_err


class BLExtract(http.Controller):

    @http.route('/steamships/bl/extract', type='http', auth='user',
                methods=['POST'], csrf=False)
    def extract(self, **post):
        """Receive a B/L scan (multipart form), return JSON.

        Provider chain:
          - Groq (if GROQ_API_KEY) → primary
          - OpenRouter (if OPENROUTER_API_KEY) → fallback chain
          - Neither set → deterministic stub data

        If `create=1` in the form, also creates a bill.of.lading record.
        """
        upload = request.httprequest.files.get('scan')
        if not upload:
            return request.make_response(
                json.dumps({'error': 'no file uploaded'}),
                headers=[('Content-Type', 'application/json')],
            )

        raw = upload.read()
        source_filename = upload.filename
        mime = upload.mimetype or 'image/jpeg'

        if GROQ_API_KEY or OPENROUTER_API_KEY:
            try:
                extracted, info = _call_with_fallback(raw, mime_type=mime)
                provider = info['provider']
                model = info['model']
                short = model.split('/')[-1].replace(':', '_').replace('.', '_')
                extracted['source'] = f'{provider}_{short}'
                extracted['__provider_used__'] = provider
                extracted['__model_used__'] = model
            except Exception as e:
                _logger.exception('All OCR providers failed, falling back to stub')
                extracted = {'error': f'all_providers_failed: {e}', 'fallback': 'stub'}
        else:
            digest = hashlib.md5(source_filename.encode()).digest()
            idx = digest[0] % len(_DEMO_RESPONSES)
            extracted = dict(_DEMO_RESPONSES[idx])
            extracted['source'] = 'stub_canned'

        extracted['source_scan_filename'] = source_filename
        extracted['groq_enabled'] = bool(GROQ_API_KEY)
        extracted['openrouter_enabled'] = bool(OPENROUTER_API_KEY)

        if post.get('create') == '1' and 'error' not in extracted:
            low_conf = extracted.get('low_confidence_fields') or []
            vals = {
                'name': extracted.get('name') or 'UNKNOWN',
                'shipper': extracted.get('shipper'),
                'consignee': extracted.get('consignee'),
                'notify_party': extracted.get('notify_party'),
                'vessel_name': extracted.get('vessel_name'),
                'voyage_number': extracted.get('voyage_number'),
                'container_numbers': extracted.get('container_numbers'),
                'port_of_loading': extracted.get('port_of_loading'),
                'port_of_discharge': extracted.get('port_of_discharge'),
                'cargo_description': extracted.get('cargo_description'),
                'gross_weight_kg': extracted.get('gross_weight_kg') or 0.0,
                'bl_date': extracted.get('bl_date') or False,
                'confidence_score': extracted.get('overall_confidence', 0.0),
                'low_confidence_fields': ','.join(low_conf),
                'source_scan_filename': source_filename,
                'state': 'pending_review',
            }
            record = request.env['bill.of.lading'].create(vals)
            extracted['record_id'] = record.id

        return request.make_response(
            json.dumps(extracted),
            headers=[('Content-Type', 'application/json')],
        )
