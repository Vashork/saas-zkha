"""Timezone settings regression tests."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.database import Base
from app.models import Setting, User
from app.timezone_settings import normalize_timezone
from app.utils import hash_password
from app.web.routes import auth, system_settings


ROOT = Path(__file__).resolve().parents[1]


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _request(path: str, *, method: str = "POST", user: User | None = None) -> Request:
    headers = []
    if user is not None:
        cookie = f"{auth.SESSION_COOKIE}={auth._sign_user_id(user.id)}"
        headers.append((b"cookie", cookie.encode("ascii")))

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers,
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_empty_receive,
    )


@pytest.fixture
async def timezone_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'timezone.db'}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        admin = User(
            username="admin",
            password_hash=hash_password("password123"),
            role="admin",
            page_permissions=None,
            is_active=True,
        )
        regular = User(
            username="regular",
            password_hash=hash_password("password123"),
            role="user",
            page_permissions="settings",
            is_active=True,
        )
        session.add_all([admin, regular])
        await session.commit()

        yield session, admin, regular

    await engine.dispose()


def test_normalize_timezone_accepts_valid_iana_name():
    assert normalize_timezone("Europe/Berlin", "Europe/Moscow") == "Europe/Berlin"


def test_normalize_timezone_falls_back_on_invalid_value():
    assert normalize_timezone("Not/AZone", "UTC") == "UTC"


def test_settings_template_exposes_notification_timezone_field():
    settings_html = (ROOT / "app" / "web" / "templates" / "settings.html").read_text(encoding="utf-8")

    assert 'action="/settings/timezone"' in settings_html
    assert 'name="notification_timezone"' in settings_html
    assert "settings.notification_timezone" in settings_html
    assert "Europe/Berlin" in settings_html


def test_scheduler_uses_db_timezone_for_notification_and_backup_jobs():
    scheduler_py = (ROOT / "app" / "scheduler.py").read_text(encoding="utf-8")

    assert 'Setting.key == "notification_timezone"' in scheduler_py
    assert "asyncio.create_task(_reschedule_notification_jobs())" in scheduler_py
    assert 'timezone=settings["timezone"]' in scheduler_py


@pytest.mark.asyncio
async def test_admin_can_save_notification_timezone(timezone_db, monkeypatch):
    session, admin, _ = timezone_db
    called = {"rescheduled": False}

    async def fake_reschedule():
        called["rescheduled"] = True

    monkeypatch.setattr(system_settings, "_reschedule_scheduler_after_timezone_change", fake_reschedule)

    response = await system_settings.save_notification_timezone(
        _request("/settings/timezone", user=admin),
        db=session,
        notification_timezone="Europe/Berlin",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings?success=")
    assert called["rescheduled"] is True

    saved_timezone = await session.scalar(
        select(Setting.value).where(Setting.key == "notification_timezone")
    )
    assert saved_timezone == "Europe/Berlin"


@pytest.mark.asyncio
async def test_non_admin_cannot_save_notification_timezone(timezone_db, monkeypatch):
    session, _, regular = timezone_db

    async def fail_reschedule():  # pragma: no cover - must not be called
        raise AssertionError("non-admin timezone change should not reschedule jobs")

    monkeypatch.setattr(system_settings, "_reschedule_scheduler_after_timezone_change", fail_reschedule)

    response = await system_settings.save_notification_timezone(
        _request("/settings/timezone", user=regular),
        db=session,
        notification_timezone="Europe/Berlin",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings?error=")

    saved_timezone = await session.scalar(
        select(Setting.value).where(Setting.key == "notification_timezone")
    )
    assert saved_timezone is None
