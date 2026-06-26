"""
CSRF protection — cookie-based double-submit token.

A per-session token is stored in a cookie and must be present
in a hidden form field ``_csrf`` on every POST/PUT/PATCH/DELETE request.
AJAX requests must include the header ``X-CSRF-Token``.

GET/HEAD/OPTIONS are always allowed (safe methods).
"""

import hmac
import secrets
import logging
from typing import Optional
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("zhkh.csrf")

CSRF_COOKIE = "_csrf"
CSRF_FIELD = "_csrf"
CSRF_HEADER = "X-CSRF-Token"

# Paths that do not require CSRF (login, logout, health)
_EXEMPT_PATHS = {"/login", "/logout", "/health"}


def _make_token() -> str:
    """Create a random CSRF token."""
    return secrets.token_hex(32)


def _constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _extract_urlencoded_token(body: bytes) -> Optional[str]:
    """Extract the CSRF token from an application/x-www-form-urlencoded body."""
    text = body.decode("utf-8", errors="replace")
    values = parse_qs(text, keep_blank_values=True).get(CSRF_FIELD)
    if not values:
        return None
    return values[0]


def _extract_multipart_token(body: bytes) -> Optional[str]:
    """Extract the CSRF token from a multipart/form-data body without consuming form parsing."""
    text = body.decode("utf-8", errors="replace")
    markers = (f'name="{CSRF_FIELD}"', f"name='{CSRF_FIELD}'")

    for marker in markers:
        marker_index = text.find(marker)
        if marker_index == -1:
            continue

        value_start = text.find("\r\n\r\n", marker_index)
        separator_len = 4
        if value_start == -1:
            value_start = text.find("\n\n", marker_index)
            separator_len = 2
        if value_start == -1:
            continue

        value_start += separator_len
        value_end = text.find("\r\n", value_start)
        if value_end == -1:
            value_end = text.find("\n", value_start)
        if value_end == -1:
            value_end = len(text)

        return text[value_start:value_end].strip()

    return None


def _extract_body_token(body: bytes, content_type: str) -> Optional[str]:
    """Extract the CSRF token from supported request body encodings."""
    if not body:
        return None

    normalized_content_type = (content_type or "").lower()
    try:
        if "multipart/form-data" in normalized_content_type:
            return _extract_multipart_token(body)
        return _extract_urlencoded_token(body)
    except Exception:
        logger.debug("Could not parse CSRF token from request body", exc_info=True)
        return None


class CsrfMiddleware(BaseHTTPMiddleware):
    """
    Double-submit CSRF middleware.

    On any GET request we issue (or refresh) the CSRF cookie.
    On any unsafe method we verify the token.
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path

        # Skip exempt paths entirely
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        if method in ("GET", "HEAD", "OPTIONS"):
            # Issue or refresh the CSRF token cookie
            response = await call_next(request)
            existing = request.cookies.get(CSRF_COOKIE)
            if not existing:
                response.set_cookie(
                    key=CSRF_COOKIE,
                    value=_make_token(),
                    httponly=False,
                    samesite="lax",
                    max_age=7 * 24 * 60 * 60,
                )
            return response

        # ---- Unsafe methods: verify token ----
        cookie_token = request.cookies.get(CSRF_COOKIE)
        if not cookie_token:
            logger.warning("CSRF token missing (cookie) — %s %s", method, path)
            return RedirectResponse(url="/?csrf=1", status_code=403)

        body: Optional[bytes] = await request.body()
        form_token = _extract_body_token(body or b"", request.headers.get("content-type", ""))
        header_token = request.headers.get(CSRF_HEADER)

        submitted_token = form_token or header_token
        if not submitted_token:
            logger.warning("CSRF token missing (field/header) — %s %s", method, path)
            return RedirectResponse(url="/?csrf=1", status_code=403)

        if not _constant_time_compare(cookie_token, submitted_token):
            logger.warning("CSRF token mismatch — %s %s", method, path)
            return RedirectResponse(url="/?csrf=1", status_code=403)

        # Reconstruct request body so downstream Form()/File() parsing still works
        request._body = body

        return await call_next(request)
