# Document AI / OCR — Day 5 + Day 6

Standalone FastAPI service (`services/document_ai_api/`) that runs
Tesseract OCR + regex extraction for **Bill of Lading** and supplier
**invoices**. Day 6 adds an **optional Gemini Vision** AI fallback for
Bill of Lading only.

The Odoo wizard lives in `custom_addons/steamships_document_ai/`. It talks
to this service via `DOCUMENT_AI_URL` (defaults to
`http://document-ai:9100`).

## Run

```bash
docker compose -f docker-compose.yml -f docker-compose.override.document-ai.yml up -d --build
```

## Health check

```bash
curl http://localhost:9100/health
# {"status":"ok","service":"steamships-document-ai"}
```

## Endpoints

* `POST /api/ocr/invoice`          — supplier invoice OCR
* `POST /api/ocr/bill-of-lading`   — Bill of Lading OCR (B/L)
* `GET  /health`                   — service status

Both `POST` endpoints accept a multipart `file=` upload (PDF, PNG, JPG).

### Response schema (B/L)

The Odoo wizard reads these top-level fields; do not remove them:

```json
{
  "document_type": "bill_of_lading",
  "detected_document_type": "bill_of_lading",
  "fields": { "bl_number": "...", "shipper": "...", ... },
  "confidence": { "bl_number": "high|medium|low", ... },
  "overall_confidence": "high|medium|low",
  "low_confidence_notes": "Please check ...",
  "raw_text": "OCR text (truncated)",
  "vision_ai_used": false,
  "vision_ai_warning": null
}
```

## Local-only mode (Python OCR only)

By default, the B/L endpoint runs **only the local Python OCR pipeline**.
Disable Gemini in `.env`:

```bash
VISION_AI_ENABLED=false
```

## Enable Gemini Vision fallback (Bill of Lading only)

Set in `.env`:

```bash
VISION_AI_ENABLED=true
VISION_AI_PROVIDER=gemini
VISION_AI_MODEL=gemini-3-flash-preview
VISION_AI_FALLBACK_MODEL=gemini-3.1-flash-lite
GEMINI_API_KEY=your_key_here
VISION_AI_TIMEOUT_S=20
```

Then restart the service so the new env vars are picked up:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.document-ai.yml up -d document-ai
```

### What the fallback does

1. **Tesseract + regex** run first (always — primary path).
2. The endpoint builds a `fields_need_ai` list from the B/L priority
   fields (see `services/document_ai_api/vision_ai.py`:
   `bl_number`, `shipper`, `consignee`, `vessel_name`, `voyage_number`,
   `container_numbers`, `port_of_loading`, `port_of_discharge`,
   `cargo_description`, `weight`, `document_date`, plus a few extras).
3. Gemini is called **only** if:

   * `VISION_AI_ENABLED=true`, AND
   * `VISION_AI_ENABLE_BOL=true` (default), AND
   * at least one priority field is empty / low-confidence / placeholder /
     invalid.

4. Gemini values are merged in-place. Existing high-confidence local
   values are **never** overwritten.
5. If Gemini fails (timeout, network, 4xx/5xx), the original Python OCR
   result is returned and a warning note is added
   (`"AI fallback failed; using local OCR result."`).

### Invoice AI fallback (off by default)

Invoices stay Python-only unless you opt in. Set:

```bash
VISION_AI_ENABLE_INVOICE=true
```

The OCR pipeline itself still runs Tesseract first; AI only fills gaps.

## Updating the Odoo module after service changes

```bash
./scripts/update-module.sh steamships_document_ai
```

## Logs

The service logs every step to stdout (captured by docker):

```text
local OCR started: endpoint=bill_of_lading, mimetype=image/jpeg
local OCR completed: endpoint=bill_of_lading, fields=22, char_count=1430
AI fallback triggered: doc_type=bill_of_lading, model=gemini-3-flash-preview, fields=3 (bl_number,cargo_description,weight)
AI fallback succeeded: model=gemini-3-flash-preview, merged=3, low_conf=0
final overall confidence: endpoint=bill_of_lading, level=medium
```

API keys are never logged.
