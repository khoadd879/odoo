"""Auth helper for the steamships-ai-api FastAPI service.

Behaviour:
- When AI_API_TOKEN is empty (local dev default), no token is required.
- When AI_API_TOKEN is set, every protected endpoint must include one of:
    X-AI-Token: <token>
    Authorization: Bearer <token>
  Mismatch / missing -> HTTP 401 with a generic detail message that does NOT
  echo the configured token.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status

from .config import Settings, get_settings


def _extract_token(
    x_ai_token: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    """Pull the token from X-AI-Token or Authorization: Bearer headers."""
    if x_ai_token:
        return x_ai_token.strip()
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    return None


def require_token(
    x_ai_token: Optional[str] = Header(default=None, alias="X-AI-Token"),
    authorization: Optional[str] = Header(default=None),
) -> None:
    """FastAPI dependency that enforces AI_API_TOKEN when configured.

    Returns nothing on success. Raises HTTP 401 on missing/wrong token.
    """
    settings = get_settings()
    if not settings.auth_required:
        return  # auth disabled

    presented = _extract_token(x_ai_token, authorization)
    if presented is None or presented != settings.ai_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid AI API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
