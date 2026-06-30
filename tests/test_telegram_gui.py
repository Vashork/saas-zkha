"""Telegram web management regression tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.database import Base
from app.models import Setting, TelegramMessageLog, TelegramOutboundMessageLog, User
from app.utils import hash_password
from app.web.routes import auth, telegram

ROOT = Path(__file__).resolve().parents[1]


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


def _request(path: str, *, method: str = "GET", user: User | None = None, query: str = "") -> Request:
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
            "query_string": query.encode("ascii"),
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_empty_receive,
    )


def _form_request(path: str, *, user: User, form: dict[str, str]) -> Request:
    cookie = f"{auth.SESSION_COOKIE}={auth._sign_user_id(user.id)}"
    body = urlencode(form).encode("ascii")
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
async def telegram_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'telegram.db'}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        admin = User(username="admin", password_hash=hash_password("password123"), role="admin", page_permissions=None, is_active=True)
        regular = User(username="regular", password_hash=hash_password("password123"), role="user", page_permissions="settings", is_active=True)
        session.add_all([admin, regular])
        await session.flush()
        session.add_all([
            TelegramMessageLog(
                telegram_user_id=111,
                username="blocked_user",
                first_name="Blocked",
                chat_id=1001,
                message_type="text",
                text="<script>alert(1)</script> blocked text",
                is_allowed=False,
                is_admin=False,
            ),
            TelegramMessageLog(
                telegram_user_id=222,
                username="allowed_user",
                first_name="Allowed",
                chat_id=1002,
                message_type="photo",
                text="allowed receipt",
                is_allowed=True,
                is_admin=False,
            ),
            TelegramMessageLog(
                telegram_user_id=333,
                username="admin_user",
                first_name="Admin",
                chat_id=1003,
                message_type="text",
                text="admin command",
                is_allowed=True,
                is_admin=True,
            ),
        ])
        await session.commit()
        yield session, admin, regular
    await engine.dispose()


def test_telegram_router_registered_and_nav_visible_for_admin():
    main_py = (ROOT / "app" / "web" / "main.py").read_text(encoding="utf-8")
    navbar = (ROOT / "app" / "web" / "templates" / "_navbar.html").read_text(encoding="utf-8")
    template = (ROOT / "app" / "web" / "templates" / "telegram.html").read_text(encoding="utf-8")

    assert "app.include_router(telegram.router)" in main_py
    assert 'href="/telegram"' in navbar
    assert 'action="/telegram/settings"' in template
    assert 'name="telegram_log_mode"' in template
    assert 'name="telegram_admin_id"' in template
    assert 'name="telegram_allowed_user_ids"' in template
    assert 'name="telegram_bot_enabled"' in template
    assert 'name="telegram_command_settings_submitted"' in template
    assert 'action="/telegram/messages/{{ m.id }}/reply"' in template
    assert 'action="/telegram/outbound/{{ out.id }}/edit"' in template
    assert template.count('<details class="card-custom telegram-section">') == 5
    assert template.count('<summary class="telegram-section-summary">') == 5
    assert '<details class="card-custom telegram-section" open' not in template
    assert "telegram-section-body" in template
    assert "line-height: 1.55" in template
    assert "TelegramMessageLog" not in template  # implementation detail stays in route, not UI text


@pytest.mark.asyncio
async def test_admin_can_view_telegram_log_filtered_by_status(telegram_db):
    session, admin, _ = telegram_db

    response = await telegram.telegram_page(
        _request("/telegram", user=admin, query="status=blocked&limit=20"),
        db=session,
        status="blocked",
        limit=20,
    )

    assert response.status_code == 200
    rows = response.context["messages"]
    assert len(rows) == 1
    assert rows[0].username == "blocked_user"
    assert response.context["filters"]["status"] == "blocked"
    assert response.context["message_status"](rows[0]) == "blocked"


@pytest.mark.asyncio
async def test_regular_user_cannot_view_telegram_gui(telegram_db):
    session, _, regular = telegram_db

    response = await telegram.telegram_page(_request("/telegram", user=regular), db=session)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"] == "/?denied=1"


@pytest.mark.asyncio
async def test_admin_can_save_telegram_log_settings_and_apply_retention(telegram_db):
    session, admin, _ = telegram_db
    old_row = TelegramMessageLog(
        telegram_user_id=444,
        username="old_user",
        chat_id=1004,
        message_type="text",
        text="old",
        is_allowed=True,
        is_admin=False,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    session.add(old_row)
    await session.commit()

    response = await telegram.save_telegram_settings(
        _request("/telegram/settings", method="POST", user=admin),
        db=session,
        telegram_log_mode="blocked",
        telegram_log_retention_days="1",
        telegram_log_retention_count="1000",
        telegram_admin_id="333",
        telegram_allowed_user_ids="222, bad, 222",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/telegram?success=")
    saved_mode = await session.scalar(select(Setting.value).where(Setting.key == "telegram_log_mode"))
    saved_days = await session.scalar(select(Setting.value).where(Setting.key == "telegram_log_retention_days"))
    saved_admin = await session.scalar(select(Setting.value).where(Setting.key == "telegram_admin_id"))
    saved_allowlist = await session.scalar(select(Setting.value).where(Setting.key == "telegram_allowed_user_ids"))
    assert saved_mode == "blocked"
    assert saved_days == "1"
    assert saved_admin == "333"
    assert saved_allowlist == "222,333"
    old_exists = await session.scalar(select(TelegramMessageLog.id).where(TelegramMessageLog.username == "old_user"))
    assert old_exists is None


@pytest.mark.asyncio
async def test_admin_can_save_telegram_runtime_command_toggles(telegram_db):
    session, admin, _ = telegram_db

    response = await telegram.save_telegram_settings(
        _form_request(
            "/telegram/settings",
            user=admin,
            form={
                "telegram_feature_settings_submitted": "1",
                "telegram_command_settings_submitted": "1",
                "telegram_admin_id": "333",
                "telegram_allowed_user_ids": "222",
                "telegram_command_help_enabled": "1",
                "telegram_command_contractors_enabled": "1",
            },
        ),
        db=session,
        telegram_feature_settings_submitted="1",
        telegram_command_settings_submitted="1",
        telegram_admin_id="333",
        telegram_allowed_user_ids="222",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    saved_bot_enabled = await session.scalar(select(Setting.value).where(Setting.key == "telegram_bot_enabled"))
    saved_help = await session.scalar(select(Setting.value).where(Setting.key == "telegram_command_help_enabled"))
    saved_balance = await session.scalar(select(Setting.value).where(Setting.key == "telegram_command_balance_enabled"))
    saved_contractors = await session.scalar(select(Setting.value).where(Setting.key == "telegram_command_contractors_enabled"))
    assert saved_bot_enabled == "0"
    assert saved_help == "1"
    assert saved_balance == "0"
    assert saved_contractors == "1"


@pytest.mark.asyncio
async def test_admin_can_reply_to_inbound_message_from_gui(telegram_db, monkeypatch):
    session, admin, _ = telegram_db

    def fake_send(token, chat_id, text):
        assert chat_id == 1001
        assert text == "Здравствуйте"
        return {"ok": True, "result": {"message_id": 555}}

    monkeypatch.setattr(telegram, "_send_bot_message", fake_send)

    response = await telegram.reply_to_telegram_message(
        1,
        _request("/telegram/messages/1/reply", method="POST", user=admin),
        db=session,
        reply_text=" Здравствуйте ",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/telegram?success=")
    outbound = await session.scalar(select(TelegramOutboundMessageLog).where(TelegramOutboundMessageLog.inbound_message_id == 1))
    assert outbound is not None
    assert outbound.status == "sent"
    assert outbound.telegram_message_id == 555
    assert outbound.text == "Здравствуйте"


@pytest.mark.asyncio
async def test_admin_can_edit_sent_bot_message_from_gui(telegram_db, monkeypatch):
    session, admin, _ = telegram_db
    outbound = TelegramOutboundMessageLog(
        inbound_message_id=1,
        actor_user_id=admin.id,
        chat_id=1001,
        telegram_message_id=555,
        text="old",
        status="sent",
    )
    session.add(outbound)
    await session.commit()

    def fake_edit(token, chat_id, message_id, text):
        assert chat_id == 1001
        assert message_id == 555
        assert text == "new text"
        return {"ok": True, "result": {"message_id": 555}}

    monkeypatch.setattr(telegram, "_edit_bot_message", fake_edit)

    response = await telegram.edit_telegram_outbound_message(
        outbound.id,
        _request(f"/telegram/outbound/{outbound.id}/edit", method="POST", user=admin),
        db=session,
        edited_text=" new text ",
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/telegram?success=")
    await session.refresh(outbound)
    assert outbound.status == "edited"
    assert outbound.is_edited is True
    assert outbound.text == "new text"
