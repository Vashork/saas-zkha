"""Audit/self-lockout regression tests for user management routes."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.database import Base
from app.models import AuditLog, User
from app.utils import hash_password
from app.web.routes import auth


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


def _assert_redirect(response, location: str) -> None:
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith(location)


@pytest.fixture
async def audit_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'user_audit.db'}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(auth, "async_session_factory", session_factory)

    async with session_factory() as session:
        admin = User(
            username="admin",
            password_hash=hash_password("password123"),
            role="admin",
            page_permissions=None,
            is_active=True,
        )
        second_admin = User(
            username="second-admin",
            password_hash=hash_password("password123"),
            role="admin",
            page_permissions=None,
            is_active=True,
        )
        operator = User(
            username="operator",
            password_hash=hash_password("password123"),
            role="operator",
            page_permissions="dashboard,settings",
            is_active=True,
        )
        session.add_all([admin, second_admin, operator])
        await session.commit()

        yield SimpleNamespace(
            session=session,
            admin=admin,
            second_admin=second_admin,
            operator=operator,
        )

    await engine.dispose()


async def _audit_entries(session, action: str) -> list[AuditLog]:
    return (
        await session.execute(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))
    ).scalars().all()


def _details(entry: AuditLog) -> dict:
    return json.loads(entry.details or "{}")


@pytest.mark.asyncio
async def test_self_deactivate_attempt_is_denied_and_audited(audit_db):
    response = await auth.toggle_user_active(
        audit_db.admin.id,
        _request(f"/settings/users/{audit_db.admin.id}/toggle-active", user=audit_db.admin),
        db=audit_db.session,
    )

    _assert_redirect(response, "/settings?error=")
    admin = await audit_db.session.get(User, audit_db.admin.id)
    assert admin.is_active is True

    entries = await _audit_entries(audit_db.session, "user_toggle_active_denied")
    assert len(entries) == 1
    assert entries[0].actor_username == "admin"
    assert entries[0].entity_id == str(audit_db.admin.id)
    assert _details(entries[0])["reason"] == "self_deactivate"


@pytest.mark.asyncio
async def test_self_admin_downgrade_attempt_is_denied_and_audited(audit_db):
    response = await auth.update_user(
        audit_db.admin.id,
        _request(f"/settings/users/{audit_db.admin.id}/update", user=audit_db.admin),
        db=audit_db.session,
        role="viewer",
        page_dashboard="on",
        page_payments="on",
        page_history="on",
        page_contractors="on",
        page_analytics="on",
        page_settings="on",
    )

    _assert_redirect(response, "/settings?error=")
    admin = await audit_db.session.get(User, audit_db.admin.id)
    assert admin.role == "admin"

    entries = await _audit_entries(audit_db.session, "user_update_denied")
    assert len(entries) == 1
    details = _details(entries[0])
    assert details["reason"] == "self_admin_downgrade"
    assert details["requested_role"] == "viewer"


@pytest.mark.asyncio
async def test_admin_delete_attempt_is_denied_and_audited(audit_db):
    response = await auth.delete_user(
        audit_db.second_admin.id,
        _request(f"/settings/users/{audit_db.second_admin.id}/delete", user=audit_db.admin),
        db=audit_db.session,
    )

    _assert_redirect(response, "/settings?error=")
    second_admin = await audit_db.session.get(User, audit_db.second_admin.id)
    assert second_admin is not None

    entries = await _audit_entries(audit_db.session, "user_delete_denied")
    assert len(entries) == 1
    assert entries[0].actor_username == "admin"
    assert entries[0].entity_id == str(audit_db.second_admin.id)
    assert _details(entries[0])["reason"] == "delete_admin"


@pytest.mark.asyncio
async def test_missing_user_management_permission_is_denied_and_audited(audit_db):
    response = await auth.create_user(
        _request("/settings/users/create", user=audit_db.operator),
        db=audit_db.session,
        username="blocked-user",
        password="password123",
        role="viewer",
        page_dashboard="on",
        page_payments="off",
        page_history="off",
        page_contractors="off",
        page_analytics="off",
        page_settings="off",
    )

    _assert_redirect(response, "/settings?error=")
    blocked_user = await audit_db.session.scalar(select(User).where(User.username == "blocked-user"))
    assert blocked_user is None

    entries = await _audit_entries(audit_db.session, "user_create_denied")
    assert len(entries) == 1
    assert entries[0].actor_username == "operator"
    details = _details(entries[0])
    assert details["reason"] == "missing_users_manage_permission"
    assert details["requested_role"] == "viewer"
    assert details["requested_username"] == "blocked-user"
