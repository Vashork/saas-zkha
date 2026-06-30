"""Telegram business-event linkage regression tests."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.bot.business_events import telegram_payment_business_details, telegram_text_hash
from app.database import Base
from app.models import AuditLog, TelegramMessageLog, User
from app.utils import hash_password
from app.web.routes import auth, telegram

ROOT = Path(__file__).resolve().parents[1]


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _request(path: str, *, user: User | None = None) -> Request:
    headers = []
    if user is not None:
        cookie = f"{auth.SESSION_COOKIE}={auth._sign_user_id(user.id)}"
        headers.append((b"cookie", cookie.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "GET",
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
async def telegram_business_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'telegram_business.db'}", echo=False)
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
        await session.flush()

        message_text = "#оплачено   #water\n#сумма:1200 #период:2026-06"
        log_row = TelegramMessageLog(
            telegram_user_id=222,
            username="payer",
            first_name="Payer",
            chat_id=1002,
            message_type="text",
            text=message_text,
            is_allowed=True,
            is_admin=False,
        )
        session.add(log_row)
        await session.flush()

        session.add(
            AuditLog(
                action="telegram_payment_recorded",
                entity_type="payment",
                entity_id="77",
                details=json.dumps(
                    {
                        "telegram_text_hash": telegram_text_hash(message_text),
                        "telegram_chat_id": 1002,
                        "telegram_user_id": 222,
                        "telegram_message_id": 555,
                        "payment_id": "77",
                        "contractor_id": "12",
                        "contractor_name": "Водоканал",
                        "amount": "1200",
                        "year": 2026,
                        "month": 6,
                        "receipt_saved": True,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )
        await session.commit()
        yield session, admin, log_row
    await engine.dispose()


def test_telegram_text_hash_is_stable_and_whitespace_normalized():
    assert telegram_text_hash("#оплачено   #water\n#сумма:1200") == telegram_text_hash(
        "#оплачено #water #сумма:1200"
    )
    assert telegram_text_hash("#оплачено #water #сумма:1200") != telegram_text_hash(
        "#оплачено #gas #сумма:1200"
    )


def test_telegram_payment_business_details_include_safe_linkage_fields():
    message = SimpleNamespace(
        message_id=555,
        text="#оплачено #water #сумма:1200",
        caption=None,
        chat=SimpleNamespace(id=1002),
        from_user=SimpleNamespace(id=222, username="payer"),
    )

    details = telegram_payment_business_details(
        message=message,
        payment_id="77",
        contractor_id="12",
        contractor_name="Водоканал",
        amount=Decimal("1200.00"),
        year=2026,
        month=6,
        receipt_path="2026/06/receipt.jpg",
    )

    assert details["telegram_chat_id"] == 1002
    assert details["telegram_user_id"] == 222
    assert details["telegram_message_id"] == 555
    assert details["telegram_text_hash"] == telegram_text_hash("#оплачено #water #сумма:1200")
    assert details["payment_id"] == "77"
    assert details["contractor_id"] == "12"
    assert details["contractor_name"] == "Водоканал"
    assert details["amount"] == "1200.00"
    assert details["year"] == 2026
    assert details["month"] == 6
    assert details["receipt_saved"] is True


@pytest.mark.asyncio
async def test_telegram_page_maps_visible_log_row_to_business_event(telegram_business_db):
    session, admin, log_row = telegram_business_db

    response = await telegram.telegram_page(_request("/telegram", user=admin), db=session)

    assert response.status_code == 200
    events = response.context["telegram_business_events"][log_row.id]
    assert len(events) == 1
    assert events[0]["action"] == "telegram_payment_recorded"
    assert events[0]["contractor_name"] == "Водоканал"
    assert events[0]["amount"] == "1200"
    assert events[0]["period"] == "2026-06"
    assert events[0]["payment_id"] == "77"
    assert events[0]["receipt_saved"] is True


def test_telegram_business_event_ui_and_handler_wiring_are_present():
    template = (ROOT / "app" / "web" / "templates" / "telegram.html").read_text(encoding="utf-8")
    handler = (ROOT / "app" / "bot" / "handlers.py").read_text(encoding="utf-8")
    route = (ROOT / "app" / "web" / "routes" / "telegram.py").read_text(encoding="utf-8")

    assert "telegram-business-events" in template
    assert "telegram_business_events.get(m.id" in template
    assert "Бизнес-события" in template
    assert "telegram_payment_recorded" in handler
    assert "telegram_payment_business_details" in handler
    assert "telegram_text_hash" in route
    assert "AuditLog.action == \"telegram_payment_recorded\"" in route
