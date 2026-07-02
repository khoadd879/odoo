"""Thin client for the stand-alone steamships-ai-api service.

Centralises:
- Base URL resolution (``RAG_API_BASE`` / ``OCR_API_BASE``).
- Optional ``X-AI-Token`` header (when ``AI_API_TOKEN`` is set).
- Multipart upload for OCR endpoints.
- A ``user-friendly error`` message when the AI service is unreachable.

The existing controllers already wrap this client with their own JSON-RPC
shape (``ok`` / ``status`` keys). Keep the wrapper behaviour unchanged so
the chatbot widget keeps working.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

_logger = logging.getLogger(__name__)


DEFAULT_RAG_BASE = "http://ai-api:9000"
DEFAULT_OCR_BASE = "http://ai-api:9000"
DEFAULT_TIMEOUT = 15.0


class AIServiceError(Exception):
    """Raised when the AI service cannot be reached or returns an error."""

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AIAPIClient:
    """Reusable HTTP client for both RAG and OCR endpoints.

    Construct once per request (the cost is negligible — just reading env
    vars) and call :meth:`retrieve` / :meth:`ocr_bill_of_lading` /
    :meth:`ocr_invoice`. Methods raise :class:`AIServiceError` on any
    non-success outcome.
    """

    def __init__(
        self,
        rag_base: Optional[str] = None,
        ocr_base: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.rag_base = (rag_base or os.environ.get("RAG_API_BASE") or DEFAULT_RAG_BASE).rstrip("/")
        self.ocr_base = (ocr_base or os.environ.get("OCR_API_BASE") or DEFAULT_OCR_BASE).rstrip("/")
        self.token = (token if token is not None else os.environ.get("AI_API_TOKEN") or "").strip()
        self.timeout = float(os.environ.get("RAG_RETRIEVE_TIMEOUT", timeout))

    # ------------------------------------------------------------------
    # Headers / helpers
    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        headers: dict[str, str] = {}
        if self.token:
            headers["X-AI-Token"] = self.token
        return headers

    def _post_json(self, url: str, payload: dict) -> dict:
        """POST JSON, raise AIServiceError on failure."""
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
        except requests.Timeout as exc:
            _logger.exception("AI API timeout after %.1fs (%s)", self.timeout, url)
            raise AIServiceError(
                "The AI service is taking too long to reply. Please try again in a moment."
            ) from exc
        except requests.ConnectionError as exc:
            _logger.exception("AI API connection error: %s", url)
            raise AIServiceError(
                "AI service is unavailable. Please check RAG_API_BASE/OCR_API_BASE."
            ) from exc
        except requests.RequestException as exc:
            _logger.exception("AI API request error: %s", exc)
            raise AIServiceError(
                "The AI service could not be reached. Please try again later."
            ) from exc
        if not resp.ok:
            _logger.error("AI API HTTP %s: %s", resp.status_code, resp.text[:300])
            raise AIServiceError(
                f"AI service returned HTTP {resp.status_code}.", status_code=resp.status_code
            )
        try:
            return resp.json()
        except ValueError as exc:
            _logger.exception("AI API returned non-JSON: %r", resp.text[:300])
            raise AIServiceError("AI service returned an unexpected response.") from exc

    def _post_multipart(self, url: str, filename: str, content: bytes, mimetype: str) -> dict:
        try:
            resp = requests.post(
                url,
                files={"file": (filename, content, mimetype or "application/octet-stream")},
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            _logger.exception("AI API OCR timeout: %s", url)
            raise AIServiceError("OCR service timeout. Please try again.") from exc
        except requests.ConnectionError as exc:
            _logger.exception("AI API OCR connection error: %s", url)
            raise AIServiceError("AI service is unavailable. Please check RAG_API_BASE/OCR_API_BASE.") from exc
        except requests.RequestException as exc:
            _logger.exception("AI API OCR request error: %s", exc)
            raise AIServiceError("OCR service could not be reached.") from exc
        if not resp.ok:
            _logger.error("AI API OCR HTTP %s: %s", resp.status_code, resp.text[:300])
            raise AIServiceError(
                f"OCR service returned HTTP {resp.status_code}.", status_code=resp.status_code
            )
        try:
            return resp.json()
        except ValueError as exc:
            _logger.exception("AI API OCR returned non-JSON: %r", resp.text[:300])
            raise AIServiceError("OCR service returned an unexpected response.") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def retrieve(self, question: str, mode: str = "staff", top_k: int = 5) -> dict:
        """Call ``POST /api/retrieve`` and return the parsed JSON."""
        payload = {"question": question, "mode": mode, "top_k": top_k}
        url = f"{self.rag_base}/api/retrieve"
        _logger.info("POST %s payload=%s", url, {"question": question, "mode": mode, "top_k": top_k})
        return self._post_json(url, payload)

    def ocr_bill_of_lading(self, filename: str, content: bytes, mimetype: str) -> dict:
        """Call ``POST /api/ocr/bill-of-lading`` and return the parsed JSON."""
        url = f"{self.ocr_base}/api/ocr/bill-of-lading"
        return self._post_multipart(url, filename, content, mimetype)

    def ocr_invoice(self, filename: str, content: bytes, mimetype: str) -> dict:
        """Call ``POST /api/ocr/invoice`` and return the parsed JSON."""
        url = f"{self.ocr_base}/api/ocr/invoice"
        return self._post_multipart(url, filename, content, mimetype)

    def health(self) -> Any:
        """Call ``GET /health`` — used by smoke checks only."""
        url = f"{self.rag_base}/health"
        resp = requests.get(url, headers=self._headers(), timeout=5.0)
        resp.raise_for_status()
        return resp.json()
