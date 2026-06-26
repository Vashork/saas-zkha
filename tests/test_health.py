"""Health endpoint tests."""

import pytest
from starlette.responses import Response

from app.web import main


class _OkResult:
    pass


class _OkSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return _OkResult()


class _FailSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        raise RuntimeError("db unavailable")


@pytest.mark.asyncio
async def test_health_check_reports_ok_when_database_ping_succeeds(monkeypatch):
    monkeypatch.setattr(main, "async_session_factory", lambda: _OkSession())

    response = Response()
    payload = await main.health_check(response)

    assert response.status_code in (None, 200)
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert "scheduler" in payload


@pytest.mark.asyncio
async def test_health_check_reports_degraded_when_database_ping_fails(monkeypatch):
    monkeypatch.setattr(main, "async_session_factory", lambda: _FailSession())

    response = Response()
    payload = await main.health_check(response)

    assert response.status_code == 500
    assert payload["status"] == "degraded"
    assert payload["database"] == "error"
