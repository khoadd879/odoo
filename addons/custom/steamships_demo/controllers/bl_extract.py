"""
Bill of Lading vision extraction endpoint.

Per DOCX B5: image/PDF upload → AI vision → JSON → B/L record.

Two modes:
  - GROQ_API_KEY set  → call Groq Llama 3.2 90B Vision (real extraction)
  - no key            → return canned stub data (deterministic per filename
                        hash) so the demo works without API access

Groq is OpenAI-compatible. We use stdlib `requests` — no extra deps.
Docs: https://console.groq.com/docs/overview
Model: llama-3.2-90b-vision-preview
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

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
GROQ_VISION_MODEL = 'meta-llama/llama-4-scout-17b-16e-instruct'  # was llama-3.2-90b-vision-preview (decommissioned)
GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions'

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


# Canned fallback (no GROQ_API_KEY) — deterministic per filename hash.
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
    """Call Groq Llama 3.2 90B Vision, return parsed JSON dict.

    Raises requests.HTTPError on API failure.
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


class BLExtract(http.Controller):

    @http.route('/steamships/bl/extract', type='http', auth='user',
                methods=['POST'], csrf=False)
    def extract(self, **post):
        """Receive a B/L scan (multipart form), return JSON.

        If GROQ_API_KEY is set, calls Llama 3.2 90B Vision.
        Otherwise returns deterministic canned data.

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

        if GROQ_API_KEY:
            try:
                extracted = _call_groq_vision(raw, mime_type=mime)
                extracted['source'] = 'groq_llama_3.2_90b_vision'
            except Exception as e:
                _logger.exception('Groq vision call failed, falling back to stub')
                extracted = {'error': f'groq_failed: {e}', 'fallback': 'stub'}
        else:
            digest = hashlib.md5(source_filename.encode()).digest()
            idx = digest[0] % len(_DEMO_RESPONSES)
            extracted = dict(_DEMO_RESPONSES[idx])
            extracted['source'] = 'stub_canned'

        extracted['source_scan_filename'] = source_filename
        extracted['groq_enabled'] = bool(GROQ_API_KEY)

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
