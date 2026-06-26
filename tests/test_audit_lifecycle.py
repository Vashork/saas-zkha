"""Audit logging for contractor and payment/transaction lifecycle events."""

import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.database import Base
from app.models import (
    AuditLog,
    Contractor,
    Payment,
    PaymentTransaction,
    User,
)
from app.utils import hash_password
from app.web.routes import auth, contractors, payments


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
            "client": ("10.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_empty_receive,
    )


@pytest.fixture
async def audit_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit-lifecycle.db'}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth, "async_session_factory", session_factory)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        admin = User(
            username="admin",
            password_hash=hash_password("password123"),
            role="admin",
            is_active=True,
        )
        contractor = Contractor(
            id="c-1",
            name="Water",
            slug="water",
            payment_type="fixed",
            fixed_amount=Decimal("100.00"),
            due_day=10,
            is_active=True,
        )
        payment = Payment(
            id="p-1",
            contractor_id="c-1",
            year=2026,
            month=6,
            amount=Decimal("100.00"),
            paid_amount=Decimal("100.00"),
            due_date=date(2026, 6, 10),
            paid_date=date(2026, 6, 5),
            status="paid",
        )
        session.add_all([admin, contractor, payment])
        await session.commit()
        yield session, session_factory, engine, admin

    await engine.dispose()


async def _latest_audit(session) -> AuditLog | None:
    return await session.scalar(select(AuditLog).order_by(AuditLog.id.desc()))


async def _add_payment_with_transaction(
    session,
    *,
    payment_id: str,
    transaction_id: str,
    amount: Decimal = Decimal("100.00"),
) -> None:
    payment = Payment(
        id=payment_id,
        contractor_id="c-1",
        year=2026,
        month=8,
        amount=Decimal("500.00"),
        paid_amount=amount,
        due_date=date(2026, 8, 10),
        paid_date=date(2026, 8, 5),
        status="pending",
    )
    tx = PaymentTransaction(
        id=transaction_id,
        payment_id=payment_id,
        amount=amount,
        paid_date=date(2026, 8, 5),
    )
    session.add_all([payment, tx])
    await session.commit()


@pytest.mark.asyncio
async def test_add_contractor_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    request = _request("/contractors/add", user=admin)

    response = await contractors.add_contractor(
        request, db=session,
        name="Gas", slug="gas", payment_type="fixed",
        fixed_amount="500", due_day=20, account_number="", description="",
    )
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "contractor_create"
    assert audit.entity_type == "contractor"
    assert audit.actor_username == "admin"


@pytest.mark.asyncio
async def test_edit_contractor_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    request = _request("/contractors/c-1/edit", user=admin)

    response = await contractors.edit_contractor(
        "c-1", request, db=session,
        name="Water Co.", payment_type="fixed",
        fixed_amount="200", due_day="15",
        account_number="", description="",
    )
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "contractor_edit"
    assert audit.entity_type == "contractor"
    assert audit.entity_id == "c-1"


@pytest.mark.asyncio
async def test_toggle_contractor_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    request = _request("/contractors/c-1/toggle", user=admin)

    response = await contractors.toggle_contractor("c-1", request, db=session)
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "contractor_toggle"
    assert audit.entity_type == "contractor"
    assert audit.entity_id == "c-1"


@pytest.mark.asyncio
async def test_delete_contractor_with_payments_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    request = _request("/contractors/c-1/delete", user=admin)

    response = await contractors.delete_contractor("c-1", request, db=session)
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "contractor_delete"
    assert audit.entity_type == "contractor"
    assert audit.entity_id == "c-1"


@pytest.mark.asyncio
async def test_hard_delete_contractor_returns_redirect_and_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    contractor = Contractor(
        id="c-hard-delete",
        name="No Payments",
        slug="no-payments",
        payment_type="variable",
        due_day=15,
        is_active=True,
    )
    session.add(contractor)
    await session.commit()

    response = await contractors.delete_contractor(
        "c-hard-delete",
        _request("/contractors/c-hard-delete/delete", user=admin),
        db=session,
    )
    assert response.status_code == 303
    assert str(response.headers.get("location", "")) == "/contractors"

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "contractor_delete"
    assert audit.entity_type == "contractor"
    assert audit.entity_id == "c-hard-delete"


@pytest.mark.asyncio
async def test_add_payment_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    request = _request("/payments/add", user=admin)

    response = await payments.add_payment(
        request, db=session,
        contractor_id="c-1", amount="", status="pending",
        paid_date_str="", year=2026, month=7, receipt=None,
    )
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "payment_create"
    assert audit.entity_type == "payment"
    assert audit.actor_username == "admin"


@pytest.mark.asyncio
async def test_delete_payment_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    request = _request("/payments/p-1/delete", user=admin)

    response = await payments.delete_payment("p-1", request, db=session)
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "payment_delete"
    assert audit.entity_type == "payment"
    assert audit.entity_id == "p-1"


@pytest.mark.asyncio
async def test_add_transaction_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    payment = Payment(
        id="p-add-tx",
        contractor_id="c-1",
        year=2026,
        month=7,
        amount=Decimal("500.00"),
        paid_amount=Decimal("0.00"),
        due_date=date(2026, 7, 10),
        status="pending",
    )
    session.add(payment)
    await session.commit()

    response = await payments.add_payment_transaction(
        "p-add-tx",
        _request("/payments/p-add-tx/transactions/add", user=admin),
        db=session,
        transaction_amount="50",
        paid_date_str="2026-07-10",
        receipt=None,
    )
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "transaction_create"
    assert audit.entity_type == "payment_transaction"


@pytest.mark.asyncio
async def test_edit_transaction_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    await _add_payment_with_transaction(session, payment_id="p-edit-tx", transaction_id="tx-edit-test")

    response = await payments.edit_payment_transaction(
        "tx-edit-test",
        _request("/payments/transactions/tx-edit-test/edit", user=admin),
        db=session,
        transaction_amount="150",
        paid_date_str="2026-08-10",
        receipt=None,
    )
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "transaction_edit"
    assert audit.entity_type == "payment_transaction"
    assert audit.entity_id == "tx-edit-test"


@pytest.mark.asyncio
async def test_delete_transaction_creates_audit_log(audit_db):
    session, factory, engine, admin = audit_db
    await _add_payment_with_transaction(session, payment_id="p-del-tx", transaction_id="tx-del-test")

    response = await payments.delete_payment_transaction(
        "tx-del-test",
        _request("/payments/transactions/tx-del-test/delete", user=admin),
        db=session,
    )
    assert response.status_code == 303

    audit = await _latest_audit(session)
    assert audit is not None
    assert audit.action == "transaction_delete"
    assert audit.entity_type == "payment_transaction"
    assert audit.entity_id == "tx-del-test"
    assert '"payment_id": "p-del-tx"' in (audit.details or "")
