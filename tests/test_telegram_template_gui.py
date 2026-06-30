"""Route/template tests for Telegram response template management UI."""

from urllib.parse import urlencode

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.database import Base
from app.models import Setting, User
from app.utils import hash_password
from app.web.routes import auth, telegram


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _form_receive(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _request(path: str, *, method: str = "GET", user: User | None = None) -> Request:
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


def _form_request(path: str, *, user: User, form: dict[str, str]) -> Request:
    cookie = f"{auth.SESSION_COOKIE}={auth._sign_user_id(user.id)}"
    body = urlencode(form).encode("utf-8")
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [
                (b"cookie", cookie.encode("ascii")),
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_form_receive(body),
    )


@pytest.fixture
async def telegram_template_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'telegram-template.db'}", echo=False)
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
        session.add(admin)
        await session.commit()
        yield session, admin
    await engine.dispose()


@pytest.mark.asyncio
async def test_telegram_page_exposes_response_template_editor_context(telegram_template_db):
    session, admin = telegram_template_db

    response = await telegram.telegram_page(_request("/telegram", user=admin), db=session)

    assert response.status_code == 200
    template_rows = response.context["telegram_response_templates"]
    names = [row["name"] for row in template_rows]
    assert "help" in names
    assert "payment_confirmation" in names
    payment_row = next(row for row in template_rows if row["name"] == "payment_confirmation")
    assert "amount" in payment_row["allowed_placeholders"]
    assert "Мосэнергосбыт" in payment_row["preview"]


@pytest.mark.asyncio
async def test_admin_can_save_telegram_response_templates(telegram_template_db):
    session, admin = telegram_template_db

    response = await telegram.save_telegram_settings(
        _form_request(
            "/telegram/settings",
            user=admin,
            form={
                "telegram_template_settings_submitted": "1",
                "telegram_template_help": "Custom help",
                "telegram_template_payment_confirmation": "OK {contractor_name} {amount} {period}{receipt_saved_line}",
            },
        ),
        db=session,
        telegram_template_settings_submitted="1",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    saved_help = await session.scalar(select(Setting.value).where(Setting.key == "telegram_template_help"))
    saved_payment = await session.scalar(select(Setting.value).where(Setting.key == "telegram_template_payment_confirmation"))
    assert saved_help == "Custom help"
    assert saved_payment == "OK {contractor_name} {amount} {period}{receipt_saved_line}"


@pytest.mark.asyncio
async def test_admin_cannot_save_template_with_unsupported_placeholder(telegram_template_db):
    session, admin = telegram_template_db

    response = await telegram.save_telegram_settings(
        _form_request(
            "/telegram/settings",
            user=admin,
            form={
                "telegram_template_settings_submitted": "1",
                "telegram_template_help": "Bad placeholder {amount}",
            },
        ),
        db=session,
        telegram_template_settings_submitted="1",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/telegram?error=")
    saved_help = await session.scalar(select(Setting.value).where(Setting.key == "telegram_template_help"))
    assert saved_help is None


def test_telegram_template_contains_editor_and_preview_wiring():
    template_html = (telegram.ROOT / "app" / "web" / "templates" / "telegram.html").read_text(encoding="utf-8") if hasattr(telegram, "ROOT") else None
    if template_html is None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        template_html = (root / "app" / "web" / "templates" / "telegram.html").read_text(encoding="utf-8")

    assert "telegram_template_settings_submitted" in template_html
    assert "telegram_response_templates" in template_html
    assert "Allowed placeholders" in template_html
    assert "tpl.preview" in template_html
