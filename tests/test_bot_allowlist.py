"""Tests for Telegram bot user allowlist."""

from types import SimpleNamespace

import pytest

from app.bot.security import TelegramAllowlistMiddleware
from app.config import Settings


class FakeMessage:
    def __init__(self, user_id: int | None):
        self.from_user = SimpleNamespace(id=user_id) if user_id is not None else None


async def _call_middleware(middleware: TelegramAllowlistMiddleware, user_id: int | None):
    called = False

    async def handler(event, data):
        nonlocal called
        called = True
        return "handled"

    result = await middleware(handler, FakeMessage(user_id), {})
    return result, called


@pytest.mark.asyncio
async def test_allowlisted_telegram_user_reaches_handler():
    middleware = TelegramAllowlistMiddleware({123})

    result, called = await _call_middleware(middleware, 123)

    assert result == "handled"
    assert called is True


@pytest.mark.asyncio
async def test_unknown_telegram_user_is_silently_ignored():
    middleware = TelegramAllowlistMiddleware({123})

    result, called = await _call_middleware(middleware, 999)

    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_empty_allowlist_ignores_all_users():
    middleware = TelegramAllowlistMiddleware(set())

    result, called = await _call_middleware(middleware, 123)

    assert result is None
    assert called is False


def test_settings_parses_telegram_allowed_user_ids(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123, 456")
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)

    settings = Settings()

    assert settings.TELEGRAM_ALLOWED_USER_IDS == {123, 456}


def test_settings_adds_telegram_admin_id_to_allowlist(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", "456")

    settings = Settings()

    assert settings.TELEGRAM_ALLOWED_USER_IDS == {123, 456}
