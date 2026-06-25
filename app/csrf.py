"""
CSRF protection — cookie-based double-submit token.

A per-session token is stored in an httponly cookie and must be present
in a hidden form field ``_csrf`` on every POST/PUT/PATCH/DELETE request.
AJAX requests must include the header ``X-CSRF-Token``.

GET/HEAD/OPTIONS are always allowed (safe methods).
"""

import hmac
import secrets
import logging
from typing import Optional

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
                    httponly=True,
                    samesite="lax",
                    max_age=7 * 24 * 60 * 60,
                )
            return response

        # ---- Unsafe methods: verify token ----
        cookie_token = request.cookies.get(CSRF_COOKIE)
        if not cookie_token:
            logger.warning("CSRF token missing (cookie) — %s %s", method, path)
            return RedirectResponse(url="/?csrf=1", status_code=403)

        # Try form field first, then header
        body: Optional[bytes] = await request.body()
        form_token = None

        if body:
            # Decode form data to look for _csrf field
            try:
                text = body.decode("utf-8", errors="replace")
                for part in text.split("&"):
                    if part.startswith(f"{CSRF_FIELD}="):
                        import urllib.parse
                        form_token = urllib.parse.unquote_plus(part.split("=", 1)[1])
                        break
            except Exception:
                pass

        header_token = request.headers.get(CSRF_HEADER)

        submitted_token = form_token or header_token
        if not submitted_token:
            logger.warning("CSRF token missing (field/header) — %s %s", method, path)
            return RedirectResponse(url="/?csrf=1", status_code=403)

        if not _constant_time_compare(cookie_token, submitted_token):
            logger.warning("CSRF token mismatch — %s %s", method, path)
            return RedirectResponse(url="/?csrf=1", status_code=403)

        # Reconstruct request body so downstream Form() parsing still works
        request._body = body

        return await call_next(request)
