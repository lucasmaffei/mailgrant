"""Bearer-token check for code that holds a FastAPI Request.

The app itself authenticates in the ASGI middleware (server.py); this helper
applies the same rule — legacy `auth.tokens` only — for callers that build
their own routes. Agents' tokens are resolved by grants.authenticate.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from .config import AuthConfig

_BEARER_PREFIX = "Bearer "


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    if not header.startswith(_BEARER_PREFIX):
        return None
    return header[len(_BEARER_PREFIX) :].strip() or None


def check_bearer(auth_cfg: AuthConfig, request: Request) -> None:
    """Validate the Authorization header against the configured token set.

    Raises 401 for missing, invalid, or unconfigured credentials.
    """
    presented = _extract_token(request)
    if presented is None:
        raise HTTPException(
            status_code=401,
            detail="missing or malformed Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    for tok in auth_cfg.tokens:
        if hmac.compare_digest(tok, presented):
            return
    raise HTTPException(
        status_code=401,
        detail="invalid Bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )
