"""
Production hardening tests — Settings validation, cookie flags, CSRF cookie flags.
"""

import importlib
import os
import sys
from unittest.mock import patch

import pytest

from app.config import Settings, _env_bool, _env_int, _env_samesite
from app.csrf import CSRF_COOKIE
from app.web.routes.auth import SESSION_COOKIE, LEGACY_COOKIES


# ---------------------------------------------------------------------------
# _env_bool / _env_int / _env_samesite helpers
# ---------------------------------------------------------------------------


def _patch_env(variables):
    """Patch os.environ with given dict, removing unrelated vars for safety."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(variables)
    return saved


def _restore_env(saved):
    os.environ.clear()
    os.environ.update(saved)


class TestEnvHelpers:
    def test_env_bool_true(self):
        saved = _patch_env({"TEST_BOOL": "true"})
        try:
            assert _env_bool("TEST_BOOL", False) is True
        finally:
            _restore_env(saved)

    def test_env_bool_false(self):
        saved = _patch_env({"TEST_BOOL": "false"})
        try:
            assert _env_bool("TEST_BOOL", True) is False
        finally:
            _restore_env(saved)

    def test_env_bool_one(self):
        saved = _patch_env({"TEST_BOOL": "1"})
        try:
            assert _env_bool("TEST_BOOL", False) is True
        finally:
            _restore_env(saved)

    def test_env_bool_default_when_missing(self):
        saved = _patch_env({})
        try:
            assert _env_bool("NONEXISTENT_VAR_XYZ", True) is True
        finally:
            _restore_env(saved)

    def test_env_int(self):
        saved = _patch_env({"TEST_INT": "42"})
        try:
            assert _env_int("TEST_INT", 0) == 42
        finally:
            _restore_env(saved)

    def test_env_int_default_when_missing(self):
        saved = _patch_env({})
        try:
            assert _env_int("NONEXISTENT_VAR_XYZ", 10) == 10
        finally:
            _restore_env(saved)

    def test_env_int_bad_value_falls_back(self):
        saved = _patch_env({"TEST_INT": "not-a-number"})
        try:
            assert _env_int("TEST_INT", 10) == 10
        finally:
            _restore_env(saved)

    def test_env_samesite_strict(self):
        saved = _patch_env({"TEST_SAME": "strict"})
        try:
            assert _env_samesite("TEST_SAME", "lax") == "strict"
        finally:
            _restore_env(saved)

    def test_env_samesite_none(self):
        saved = _patch_env({"TEST_SAME": "none"})
        try:
            assert _env_samesite("TEST_SAME", "lax") == "none"
        finally:
            _restore_env(saved)

    def test_env_samesite_invalid_falls_back(self):
        saved = _patch_env({"TEST_SAME": "garbage"})
        try:
            assert _env_samesite("TEST_SAME", "lax") == "lax"
        finally:
            _restore_env(saved)


# ---------------------------------------------------------------------------
# Settings validation — production rejects unsafe defaults
# ---------------------------------------------------------------------------


def _build_settings(**overrides):
    """Build a fresh Settings instance with overridden env vars."""
    env = {
        "APP_ENV": "production",
        "SECRET_KEY": "super-secret-key",
        "ADMIN_PASSWORD": "strong-admin-pw",
        "USER_PASSWORD": "strong-user-pw",
        "COOKIE_SECURE": "true",
        "COOKIE_SAMESITE": "lax",
    }
    env.update(overrides)
    saved = _patch_env(env)
    try:
        return Settings()
    finally:
        _restore_env(saved)


class TestProductionValidation:
    def test_production_rejects_default_secret_key(self):
        settings = _build_settings(SECRET_KEY="change-me-in-production")
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            settings.validate_for_startup()

    def test_production_rejects_empty_secret_key(self):
        settings = _build_settings(SECRET_KEY="")
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            settings.validate_for_startup()

    def test_production_rejects_env_example_secret_key(self):
        settings = _build_settings(SECRET_KEY="change-me-to-a-random-string")
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            settings.validate_for_startup()

    def test_production_rejects_default_admin_password(self):
        settings = _build_settings(ADMIN_PASSWORD="admin")
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            settings.validate_for_startup()

    def test_production_rejects_default_user_password(self):
        settings = _build_settings(USER_PASSWORD="user")
        with pytest.raises(RuntimeError, match="USER_PASSWORD"):
            settings.validate_for_startup()

    def test_production_rejects_samesite_none_without_secure(self):
        settings = _build_settings(COOKIE_SAMESITE="none", COOKIE_SECURE="false")
        with pytest.raises(RuntimeError, match="COOKIE_SAMESITE"):
            settings.validate_for_startup()

    def test_production_accepts_valid_config(self):
        settings = _build_settings()
        settings.validate_for_startup()  # no exception

    def test_development_defaults_do_not_raise(self):
        saved = _patch_env({"APP_ENV": "development"})
        try:
            settings = Settings()
            settings.validate_for_startup()  # no exception
        finally:
            _restore_env(saved)

    def test_error_messages_do_not_leak_secrets(self):
        """Exception messages must never contain actual secret values."""
        settings = _build_settings(SECRET_KEY="change-me-in-production")
        with pytest.raises(RuntimeError) as exc_info:
            settings.validate_for_startup()
        msg = str(exc_info.value)
        assert "change-me-in-production" not in msg


# ---------------------------------------------------------------------------
# auth._set_session_cookies uses settings flags
# ---------------------------------------------------------------------------


class TestAuthCookieFlags:
    def _mock_settings(self, secure=True, httponly=True, samesite="lax", max_age=604800):
        from types import SimpleNamespace
        return SimpleNamespace(
            COOKIE_SECURE=secure,
            COOKIE_HTTPONLY=httponly,
            COOKIE_SAMESITE=samesite,
            SESSION_COOKIE_MAX_AGE_SECONDS=max_age,
            SECRET_KEY="test-secret",
        )

    def test_set_session_cookies_secure_flag(self):
        from starlette.responses import RedirectResponse
        from app.web.routes import auth as auth_module
        from types import SimpleNamespace

        mock_settings = self._mock_settings(secure=True, samesite="strict")
        with patch.object(auth_module, "get_settings", return_value=mock_settings):
            resp = RedirectResponse(url="/")
            fake_user = SimpleNamespace(id=1, username="alice", role="user", page_permissions="dashboard")
            auth_module._set_session_cookies(resp, fake_user)

            # Check session cookie
            session_header = dict(resp.headers).get("set-cookie", "")
            assert "Secure" in session_header
            assert "samesite=strict" in session_header.lower()
            assert "max-age=604800" in session_header.lower()

    def test_set_session_cookies_insecure_flag(self):
        from starlette.responses import RedirectResponse
        from app.web.routes import auth as auth_module
        from types import SimpleNamespace

        mock_settings = self._mock_settings(secure=False, samesite="lax")
        with patch.object(auth_module, "get_settings", return_value=mock_settings):
            resp = RedirectResponse(url="/")
            fake_user = SimpleNamespace(id=2, username="bob", role="admin", page_permissions=None)
            auth_module._set_session_cookies(resp, fake_user)

            session_header = dict(resp.headers).get("set-cookie", "")
            assert "Secure" not in session_header
            assert "samesite=lax" in session_header.lower()


# ---------------------------------------------------------------------------
# csrf CsrfMiddleware sets Secure flag on CSRF cookie
# ---------------------------------------------------------------------------


class TestCsrfCookieFlags:
    def _make_get_request(self):
        from starlette.requests import Request

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "query_string": b"",
                "client": ("127.0.0.1", 50000),
                "server": ("localhost", 80),
                "scheme": "http",
            },
            receive=receive,
        )

    @pytest.mark.asyncio
    async def test_csrf_cookie_secure_when_production(self):
        from app.csrf import CsrfMiddleware
        from types import SimpleNamespace

        mock_settings = SimpleNamespace(
            COOKIE_SECURE=True,
            COOKIE_HTTPONLY=True,
            COOKIE_SAMESITE="strict",
            SESSION_COOKIE_MAX_AGE_SECONDS=3600,
        )

        middleware = CsrfMiddleware(
            app=lambda request: type("Response", (), {
                "body": b"",
                "status_code": 200,
                "headers": [],
                "set_cookie": lambda **kw: None,
            })(),
        )

        # Patch get_settings at module level
        import app.csrf as csrf_module

        set_cookies_called = []

        class CaptureResponse:
            status_code = 200
            body = b""
            headers = []
            def set_cookie(self, **kw):
                set_cookies_called.append(kw)

        async def dummy_app(request):
            return CaptureResponse()

        middleware = CsrfMiddleware(app=dummy_app)
        request = self._make_get_request()

        with patch.object(csrf_module, "get_settings", return_value=mock_settings):
            response = await middleware.dispatch(request, dummy_app)

        # CSRF cookie should have been set
        assert len(set_cookies_called) == 1
        cookie_kw = set_cookies_called[0]
        assert cookie_kw["secure"] is True
        assert cookie_kw["samesite"] == "strict"
        assert cookie_kw["max_age"] == 3600
        assert cookie_kw["httponly"] is False

    @pytest.mark.asyncio
    async def test_csrf_cookie_insecure_when_development(self):
        from app.csrf import CsrfMiddleware
        from types import SimpleNamespace

        mock_settings = SimpleNamespace(
            COOKIE_SECURE=False,
            COOKIE_HTTPONLY=True,
            COOKIE_SAMESITE="lax",
            SESSION_COOKIE_MAX_AGE_SECONDS=604800,
        )

        set_cookies_called = []

        class CaptureResponse:
            status_code = 200
            body = b""
            headers = []
            def set_cookie(self, **kw):
                set_cookies_called.append(kw)

        async def dummy_app(request):
            return CaptureResponse()

        middleware = CsrfMiddleware(app=dummy_app)
        request = self._make_get_request()

        import app.csrf as csrf_module

        with patch.object(csrf_module, "get_settings", return_value=mock_settings):
            response = await middleware.dispatch(request, dummy_app)

        assert len(set_cookies_called) == 1
        cookie_kw = set_cookies_called[0]
        assert cookie_kw["secure"] is False
        assert cookie_kw["samesite"] == "lax"
        assert cookie_kw["max_age"] == 604800
        assert cookie_kw["httponly"] is False
