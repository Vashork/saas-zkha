"""Route-level permission matrix regression tests."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.database import Base
from app.models import Contractor, User
from app.utils import hash_password
from app.web.permissions import BACKUPS_MANAGE
from app.web.routes import auth, backups, contractors


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


def _is_redirect_to(response, location: str) -> bool:
    return (
        isinstance(response, RedirectResponse)
        and response.status_code == 303
        and response.headers["location"].startswith(location)
    )


@pytest.fixture
async def route_matrix_db(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(auth, "async_session_factory", session_factory)

    async with session_factory() as session:
        users = {
            "admin": User(
                username="admin",
                password_hash=hash_password("password123"),
                role="admin",
                page_permissions=None,
                is_active=True,
            ),
            "operator": User(
                username="operator",
                password_hash=hash_password("password123"),
                role="operator",
                page_permissions="dashboard,payments,history,contractors,analytics",
                is_active=True,
            ),
            "viewer": User(
                username="viewer",
                password_hash=hash_password("password123"),
                role="viewer",
                page_permissions="dashboard,settings",
                is_active=True,
            ),
            "legacy": User(
                username="legacy",
                password_hash=hash_password("password123"),
                role="user",
                page_permissions=None,
                is_active=True,
            ),
            "empty_viewer": User(
                username="empty-viewer",
                password_hash=hash_password("password123"),
                role="viewer",
                page_permissions="",
                is_active=True,
            ),
        }
        session.add_all(users.values())
        await session.commit()

        yield SimpleNamespace(session=session, users=users)

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_key", "page_slug", "allowed"),
    [
        ("admin", "settings", True),
        ("admin", "contractors", True),
        ("operator", "contractors", True),
        ("operator", "settings", False),
        ("viewer", "dashboard", True),
        ("viewer", "contractors", False),
        ("legacy", "settings", True),
        ("legacy", "contractors", True),
        ("empty_viewer", "dashboard", False),
        ("empty_viewer", "settings", False),
    ],
)
async def test_require_page_uses_database_page_visibility(route_matrix_db, user_key, page_slug, allowed):
    user = route_matrix_db.users[user_key]

    response = await auth._require_page(_request(f"/{page_slug}", method="GET", user=user), page_slug)

    if allowed:
        assert response is None
    else:
        assert _is_redirect_to(response, "/?denied=1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_key", "allowed"),
    [
        ("admin", True),
        ("operator", True),
        ("viewer", False),
        ("legacy", False),
    ],
)
async def test_contractor_business_mutation_route_allows_admin_and_operator_only(
    route_matrix_db,
    user_key,
    allowed,
):
    user = route_matrix_db.users[user_key]
    slug = f"matrix-{user_key}"

    response = await contractors.add_contractor(
        _request("/contractors/add", user=user),
        db=route_matrix_db.session,
        name=f"Matrix {user_key}",
        slug=slug,
        payment_type="fixed",
        fixed_amount="100.00",
        due_day=15,
        account_number="",
        description="",
    )

    contractor = await route_matrix_db.session.scalar(select(Contractor).where(Contractor.slug == slug))
    if allowed:
        assert _is_redirect_to(response, "/contractors")
        assert contractor is not None
    else:
        assert _is_redirect_to(response, "/contractors?error=")
        assert contractor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_key", "allowed"),
    [
        ("admin", True),
        ("operator", False),
        ("viewer", False),
        ("legacy", False),
    ],
)
async def test_create_user_system_route_allows_admin_only(route_matrix_db, user_key, allowed):
    user = route_matrix_db.users[user_key]
    username = f"created-by-{user_key}"

    response = await auth.create_user(
        _request("/settings/users/create", user=user),
        db=route_matrix_db.session,
        username=username,
        password="password123",
        role="viewer",
        page_dashboard="on",
        page_payments="off",
        page_history="off",
        page_contractors="off",
        page_analytics="off",
        page_settings="off",
    )

    created_user = await route_matrix_db.session.scalar(select(User).where(User.username == username))
    if allowed:
        assert _is_redirect_to(response, "/settings?success=")
        assert created_user is not None
    else:
        assert _is_redirect_to(response, "/settings?error=")
        assert created_user is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_key", "allowed"),
    [
        ("admin", True),
        ("operator", False),
        ("viewer", False),
        ("legacy", False),
    ],
)
async def test_backups_manage_helper_allows_admin_only(route_matrix_db, user_key, allowed):
    user = route_matrix_db.users[user_key]

    current_user, redirect = await backups._require_action_user(
        _request("/backups/create", user=user),
        route_matrix_db.session,
        BACKUPS_MANAGE,
    )

    assert current_user.username == user.username
    if allowed:
        assert redirect is None
    else:
        assert _is_redirect_to(redirect, "/?denied=1")
