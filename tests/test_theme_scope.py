"""Theme scope regression tests."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.database import Base
from app.models import Setting, User
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
async def theme_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'theme.db'}", echo=False)
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


def test_system_settings_router_is_registered_before_legacy_auth_router():
    main_py = (ROOT / "app" / "web" / "main.py").read_text(encoding="utf-8")

    system_pos = main_py.index("app.include_router(system_settings.router)")
    auth_pos = main_py.index("app.include_router(auth.router)")

    assert system_pos < auth_pos


@pytest.mark.asyncio
async def test_admin_can_change_global_theme(theme_db):
    session, admin, _ = theme_db

    response = await system_settings.change_global_theme(
        _request("/settings/theme", user=admin),
        data={"theme": "light"},
        db=session,
    )

    assert response.status_code == 200
    saved_theme = await session.scalar(select(Setting.value).where(Setting.key == "ui_theme"))
    assert saved_theme == "light"


@pytest.mark.asyncio
async def test_non_admin_cannot_change_global_theme(theme_db):
    session, _, regular = theme_db

    response = await system_settings.change_global_theme(
        _request("/settings/theme", user=regular),
        data={"theme": "light"},
        db=session,
    )

    assert response.status_code == 403
    saved_theme = await session.scalar(select(Setting.value).where(Setting.key == "ui_theme"))
    assert saved_theme is None


@pytest.mark.asyncio
async def test_invalid_global_theme_falls_back_to_dark(theme_db):
    session, admin, _ = theme_db

    response = await system_settings.change_global_theme(
        _request("/settings/theme", user=admin),
        data={"theme": "unexpected"},
        db=session,
    )

    assert response.status_code == 200
    saved_theme = await session.scalar(select(Setting.value).where(Setting.key == "ui_theme"))
    assert saved_theme == "dark"
