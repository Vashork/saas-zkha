"""Permission regression tests for web routes."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.database import Base
from app.models import Contractor, Payment, PaymentTransaction, User
from app.utils import hash_password
from app.web.main import enforce_page_permissions
from app.web.routes import auth, contractors, payments


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


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


def _assert_redirect(response, location: str) -> None:
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith(location)


@pytest.fixture
async def permission_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'permissions.db'}", echo=False)
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
        restricted = User(
            username="restricted",
            password_hash=hash_password("password123"),
            role="user",
            page_permissions="dashboard",
            is_active=True,
        )
        settings_user = User(
            username="settings-user",
            password_hash=hash_password("password123"),
            role="user",
            page_permissions="dashboard,settings",
            is_active=True,
        )
        contractor = Contractor(
            id="contractor-1",
            name="Water",
            slug="water",
            payment_type="fixed",
            fixed_amount=Decimal("100.00"),
            due_day=10,
            is_active=True,
        )
        variable_contractor = Contractor(
            id="contractor-variable",
            name="Hot Water",
            slug="hot-water",
            payment_type="variable",
            fixed_amount=None,
            due_day=25,
            is_active=True,
        )
        payment = Payment(
            id="payment-1",
            contractor_id="contractor-1",
            year=2026,
            month=6,
            amount=Decimal("100.00"),
            paid_amount=None,
            due_date=date(2026, 6, 10),
            status="pending",
        )
        variable_payment = Payment(
            id="payment-variable",
            contractor_id="contractor-variable",
            year=2026,
            month=6,
            amount=Decimal("6700.00"),
            paid_amount=Decimal("6700.00"),
            due_date=date(2026, 6, 25),
            paid_date=date(2026, 6, 25),
            status="paid",
        )
        session.add_all([admin, restricted, settings_user, contractor, variable_contractor, payment, variable_payment])
        await session.commit()

        yield SimpleNamespace(
            session=session,
            admin=admin,
            restricted=restricted,
            settings_user=settings_user,
            contractor=contractor,
            variable_contractor=variable_contractor,
            payment=payment,
            variable_payment=variable_payment,
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_unauthenticated_user_is_redirected_to_login(permission_db):
    response = await auth._require_page(_request("/payments"), "payments")

    _assert_redirect(response, "/login")


@pytest.mark.asyncio
async def test_restricted_user_cannot_get_settings(permission_db):
    call_next_was_called = False

    async def call_next(request):
        nonlocal call_next_was_called
        call_next_was_called = True
        return Response("allowed")

    response = await enforce_page_permissions(
        _request("/settings", user=permission_db.restricted),
        call_next,
    )

    _assert_redirect(response, "/?denied=1")
    assert call_next_was_called is False


@pytest.mark.asyncio
async def test_non_admin_cannot_use_user_management_endpoints(permission_db):
    request = _request("/settings/users/create", method="POST", user=permission_db.settings_user)

    create_response = await auth.create_user(
        request,
        db=permission_db.session,
        username="blocked-user",
        password="password123",
        role="user",
        page_dashboard="on",
        page_payments="off",
        page_history="off",
        page_contractors="off",
        page_analytics="off",
        page_settings="off",
    )
    _assert_redirect(create_response, "/settings?error=")

    blocked = await permission_db.session.scalar(select(User).where(User.username == "blocked-user"))
    assert blocked is None

    update_response = await auth.update_user(
        permission_db.admin.id,
        request,
        db=permission_db.session,
        role="user",
        page_dashboard="on",
        page_payments="on",
        page_history="on",
        page_contractors="on",
        page_analytics="on",
        page_settings="on",
    )
    _assert_redirect(update_response, "/settings?error=")

    admin = await permission_db.session.get(User, permission_db.admin.id)
    assert admin.role == "admin"


@pytest.mark.asyncio
async def test_restricted_user_cannot_mutate_contractors_or_payments(permission_db):
    request = _request("/contractors/add", method="POST", user=permission_db.restricted)

    contractor_response = await contractors.add_contractor(
        request,
        db=permission_db.session,
        name="Blocked contractor",
        slug="blocked-contractor",
        payment_type="fixed",
        fixed_amount="10",
        due_day=5,
        account_number="",
        description="",
    )
    _assert_redirect(contractor_response, "/contractors?error=")

    blocked_contractor = await permission_db.session.scalar(
        select(Contractor).where(Contractor.slug == "blocked-contractor")
    )
    assert blocked_contractor is None

    payment_response = await payments.delete_payment(
        permission_db.payment.id,
        request,
        db=permission_db.session,
    )
    _assert_redirect(payment_response, "/payments?error=")

    existing_payment = await permission_db.session.get(Payment, permission_db.payment.id)
    assert existing_payment is not None


@pytest.mark.asyncio
async def test_admin_can_perform_expected_user_contractor_and_payment_actions(permission_db):
    request = _request("/settings/users/create", method="POST", user=permission_db.admin)

    user_response = await auth.create_user(
        request,
        db=permission_db.session,
        username="new-user",
        password="password123",
        role="user",
        page_dashboard="on",
        page_payments="off",
        page_history="off",
        page_contractors="off",
        page_analytics="off",
        page_settings="off",
    )
    _assert_redirect(user_response, "/settings?success=")

    created_user = await permission_db.session.scalar(select(User).where(User.username == "new-user"))
    assert created_user is not None
    assert created_user.role == "user"

    contractor_response = await contractors.add_contractor(
        _request("/contractors/add", method="POST", user=permission_db.admin),
        db=permission_db.session,
        name="Power",
        slug="power",
        payment_type="fixed",
        fixed_amount="250.50",
        due_day=15,
        account_number="",
        description="",
    )
    _assert_redirect(contractor_response, "/contractors")

    power = await permission_db.session.scalar(select(Contractor).where(Contractor.slug == "power"))
    assert power is not None

    payment_response = await payments.add_payment(
        _request("/payments/add", method="POST", user=permission_db.admin),
        db=permission_db.session,
        contractor_id=power.id,
        amount="",
        status="pending",
        paid_date_str="",
        year=2026,
        month=7,
        receipt=None,
    )
    _assert_redirect(payment_response, "/payments?year=2026&month=7")

    created_payment = await permission_db.session.scalar(
        select(Payment).where(
            Payment.contractor_id == power.id,
            Payment.year == 2026,
            Payment.month == 7,
        )
    )
    assert created_payment is not None
    assert created_payment.amount == Decimal("250.50")


@pytest.mark.asyncio
async def test_variable_payment_top_up_above_current_balance_increases_charge(permission_db):
    response = await payments.add_payment_transaction(
        permission_db.variable_payment.id,
        _request("/payments/payment-variable/transactions/add", method="POST", user=permission_db.admin),
        db=permission_db.session,
        transaction_amount="1000",
        paid_date_str="2026-06-26",
        receipt=None,
    )

    _assert_redirect(response, "/payments?year=2026&month=6")

    payment = await permission_db.session.get(Payment, permission_db.variable_payment.id)
    assert payment.amount == Decimal("7700.00")
    assert payment.paid_amount == Decimal("7700.00")
    assert payment.status == "paid"

    transactions = (
        await permission_db.session.execute(
            select(PaymentTransaction).where(PaymentTransaction.payment_id == payment.id)
        )
    ).scalars().all()
    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("1000.00")
