# -*- coding: utf-8 -*-
import base64
import json
import logging
import os
import urllib.error
import urllib.request

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Default to the unified AI API on port 9000. The legacy ``document-ai:9100``
# hostname still works for the old stand-alone OCR container until that
# service is folded into ``services/steamships-ai-api``.
DEFAULT_OCR_URL = "http://ai-api:9000"
OCR_TIMEOUT_SECONDS = 60

ENDPOINT_MAP = {
    "invoice": "/api/ocr/invoice",
    "bill_of_lading": "/api/ocr/bill-of-lading",
}


class SteamshipsDocumentUploadWizard(models.TransientModel):
    _name = "steamships.document.upload.wizard"
    _description = "Upload Document for OCR"

    document_type = fields.Selection(
        [
            ("invoice", "Supplier Invoice"),
            ("bill_of_lading", "Bill of Lading"),
        ],
        string="Document Type",
        required=True,
        default="invoice",
    )
    file = fields.Binary(string="File", required=True)
    filename = fields.Char(string="Filename")
    mimetype = fields.Char(string="MIME Type")

    # ------------------------------------------------------------------
    # OCR endpoint lookup
    # ------------------------------------------------------------------
    def _ocr_base_url(self):
        # ``OCR_API_BASE`` is the unified AI API URL; ``DOCUMENT_AI_URL`` is
        # kept as a fallback so the legacy ``document-ai:9100`` override
        # still works during the migration window.
        return (
            os.environ.get("OCR_API_BASE")
            or os.environ.get("DOCUMENT_AI_URL")
            or DEFAULT_OCR_URL
        ).rstrip("/") + "/"

    def _ocr_token(self):
        return (
            os.environ.get("AI_API_TOKEN")
            or os.environ.get("OCR_API_TOKEN")
            or ""
        ).strip()

    def _build_endpoint(self):
        ep = ENDPOINT_MAP.get(self.document_type)
        if not ep:
            raise UserError(_("Unsupported document type."))
        return self._ocr_base_url() + ep.lstrip("/")

    # ------------------------------------------------------------------
    # Minimal stdlib multipart uploader — avoids needing `requests` in the
    # Odoo container.
    # ------------------------------------------------------------------
    @staticmethod
    def _encode_multipart(filename, content_bytes, mimetype):
        boundary = "----odoo-doc-ai-boundary-9f3b8c"
        crlf = b"\r\n"
        parts = [
            b"--" + boundary.encode() + crlf,
            (
                'Content-Disposition: form-data; name="file"; filename="'
                + filename.replace('"', "")
                + '"'
            ).encode() + crlf,
            ("Content-Type: " + mimetype).encode() + crlf + crlf,
            content_bytes + crlf,
            b"--" + boundary.encode() + b"--" + crlf,
        ]
        body = b"".join(parts)
        headers = {
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Content-Length": str(len(body)),
        }
        return body, headers

    def _post_file(self, endpoint, filename, content_bytes, mimetype):
        body, headers = self._encode_multipart(filename, content_bytes, mimetype)
        token = self._ocr_token()
        if token:
            headers["X-AI-Token"] = token
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=OCR_TIMEOUT_SECONDS) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            body_preview = exc.read().decode("utf-8", "replace")[:200] if exc.fp else ""
            if exc.code == 401:
                raise UserError(
                    _(
                        "OCR service returned HTTP 401. Please check the "
                        "AI_API_TOKEN env value shared between Odoo and the "
                        "AI API."
                    )
                ) from exc
            raise UserError(
                _("OCR service returned HTTP %s: %s") % (exc.code, body_preview)
            ) from exc
        except urllib.error.URLError as exc:
            # URLError wraps timeouts and DNS / connection refused.
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise UserError(_("OCR service timeout. Please try again.")) from exc
            raise UserError(
                _(
                    "OCR service is unavailable. Please check RAG_API_BASE/OCR_API_BASE. "
                    "(%s)"
                )
                % (reason or exc)
            ) from exc
        except TimeoutError as exc:
            raise UserError(_("OCR service timeout. Please try again.")) from exc

    # ------------------------------------------------------------------
    # Main button
    # ------------------------------------------------------------------
    def action_upload_extract(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Please choose a file to upload."))

        filename = self.filename or "upload.bin"
        mimetype = self.mimetype or "application/octet-stream"

        try:
            file_bytes = base64.b64decode(self.file)
        except Exception as exc:  # pragma: no cover - defensive
            raise UserError(_("Could not read uploaded file: %s") % exc) from exc

        endpoint = self._build_endpoint()
        _logger.info("steamships_document_ai: posting %s to %s", filename, endpoint)

        status, raw = self._post_file(endpoint, filename, file_bytes, mimetype)
        if status != 200:
            raise UserError(
                _("OCR service returned HTTP %s: %s") % (status, raw[:200].decode("utf-8", "replace"))
            )

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise UserError(_("OCR service returned invalid JSON.")) from exc

        # ---- Document-type guard --------------------------------------------
        # OCR may signal an explicit error (mismatch / unknown) or simply
        # disagree with the user's choice. Either way we refuse to write a
        # wrong-model record.
        if isinstance(payload, dict) and payload.get("error"):
            raise UserError(payload.get("message") or _("OCR service rejected the document."))

        detected = (
            payload.get("detected_document_type")
            or payload.get("document_type")
            or ""
        ).lower()

        if self.document_type == "invoice" and detected != "invoice":
            raise UserError(
                _(
                    "This document was detected as '%(detected)s', not an "
                    "invoice. Please re-upload it under the correct document "
                    "type."
                )
                % {"detected": detected or "unknown"}
            )
        if self.document_type == "bill_of_lading" and detected != "bill_of_lading":
            raise UserError(
                _(
                    "This document was detected as '%(detected)s', not a Bill "
                    "of Lading. Please re-upload it under the correct document "
                    "type."
                )
                % {"detected": detected or "unknown"}
            )

        # ``self.file`` is already a base64 string — keep it as-is for the
        # Binary field.
        file_content = self.file

        if self.document_type == "invoice":
            record = self.env["steamships.invoice.ocr"].create({})
            record.populate_from_ocr(payload, file_content, filename, mimetype)
            return self._open_record(
                "steamships.invoice.ocr",
                record.id,
                "view_steamships_invoice_ocr_form",
            )

        record = self.env["steamships.bill.lading"].create({})
        record.populate_from_ocr(payload, file_content, filename, mimetype)
        return self._open_record(
            "steamships.bill.lading",
            record.id,
            "view_steamships_bill_lading_form",
        )

    # ------------------------------------------------------------------
    # Action helpers
    # ------------------------------------------------------------------
    def _open_record(self, model_name, record_id, view_xml_id):
        view = self.env.ref(
            "steamships_document_ai." + view_xml_id,
            raise_if_not_found=False,
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": model_name,
            "res_id": record_id,
            "view_mode": "form",
            "view_type": "form",
            "views": [(view.id, "form")] if view else [(False, "form")],
            "target": "current",
        }
