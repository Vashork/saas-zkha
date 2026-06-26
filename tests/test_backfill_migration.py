"""Tests for the backfill migration of PaymentTransaction records.

The migration in init_db._run_migrations creates PaymentTransaction rows
for legacy Payment records where paid_amount > 0 but no transactions exist.
"""

import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.database import Base
from app.models import Payment, PaymentTransaction, Contractor
from init_db import _run_migrations


@pytest.fixture
def _tmp_engine(tmp_path):
    """Create a fresh engine for each test."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'backfill.db'}", echo=False)
    return engine


async def _setup_db(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        contractor = Contractor(
            id="c-1",
            name="Electricity",
            slug="electricity",
            payment_type="fixed",
            fixed_amount=Decimal("3200.00"),
            due_day=10,
            is_active=True,
        )
        session.add(contractor)
        await session.commit()
    return session_factory


@pytest.mark.asyncio
async def test_backfill_creates_transactions_for_paid_payments(_tmp_engine):
    engine = _tmp_engine
    factory = await _setup_db(engine)

    async with factory() as session:
        payment = Payment(
            id="pay-legacy-1",
            contractor_id="c-1",
            year=2025,
            month=1,
            amount=Decimal("3200.00"),
            paid_amount=Decimal("3200.00"),
            due_date=date(2025, 1, 10),
            paid_date=date(2025, 1, 8),
            receipt_file="receipts/2025/01/legacy.pdf",
            status="paid",
        )
        session.add(payment)
        await session.commit()

    async with engine.begin() as conn:
        await conn.run_sync(_run_migrations)

    async with factory() as session:
        result = await session.execute(
            select(Payment).options(selectinload(Payment.transactions)).where(Payment.id == "pay-legacy-1")
        )
        payment = result.scalar_one()
        assert len(payment.transactions) == 1
        tx = payment.transactions[0]
        assert tx.id == f"tx-backfill-{payment.id}"
        assert tx.amount == Decimal("3200.00")
        assert tx.paid_date == payment.paid_date
        assert tx.receipt_file == "receipts/2025/01/legacy.pdf"
        assert tx.notes == "Backfilled from legacy payment fields"

    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_skips_unpaid_payments(_tmp_engine):
    engine = _tmp_engine
    factory = await _setup_db(engine)

    async with factory() as session:
        payment = Payment(
            id="pay-unpaid",
            contractor_id="c-1",
            year=2025,
            month=2,
            amount=Decimal("3200.00"),
            paid_amount=None,
            due_date=date(2025, 2, 10),
            status="pending",
        )
        session.add(payment)
        await session.commit()

    async with engine.begin() as conn:
        await conn.run_sync(_run_migrations)

    async with factory() as session:
        result = await session.execute(
            select(Payment).options(selectinload(Payment.transactions)).where(Payment.id == "pay-unpaid")
        )
        payment = result.scalar_one()
        assert len(payment.transactions) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_skips_payments_that_already_have_transactions(_tmp_engine):
    engine = _tmp_engine
    factory = await _setup_db(engine)

    async with factory() as session:
        payment = Payment(
            id="pay-has-tx",
            contractor_id="c-1",
            year=2025,
            month=3,
            amount=Decimal("3200.00"),
            paid_amount=Decimal("1000.00"),
            due_date=date(2025, 3, 10),
            paid_date=date(2025, 3, 5),
            status="pending",
        )
        tx = PaymentTransaction(
            id="tx-existing",
            payment_id=payment.id,
            amount=Decimal("1000.00"),
            paid_date=date(2025, 3, 5),
        )
        session.add_all([payment, tx])
        await session.commit()

    async with engine.begin() as conn:
        await conn.run_sync(_run_migrations)

    async with factory() as session:
        result = await session.execute(
            select(PaymentTransaction).where(PaymentTransaction.payment_id == "pay-has-tx")
        )
        txs = result.scalars().all()
        assert len(txs) == 1
        assert txs[0].id == "tx-existing"

    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_is_idempotent(_tmp_engine):
    engine = _tmp_engine
    factory = await _setup_db(engine)

    async with factory() as session:
        payment = Payment(
            id="pay-idem",
            contractor_id="c-1",
            year=2025,
            month=4,
            amount=Decimal("500.00"),
            paid_amount=Decimal("500.00"),
            due_date=date(2025, 4, 10),
            paid_date=date(2025, 4, 1),
            status="paid",
        )
        session.add(payment)
        await session.commit()

    # Run migration first time
    async with engine.begin() as conn:
        await conn.run_sync(_run_migrations)
    # Run migration second time
    async with engine.begin() as conn:
        await conn.run_sync(_run_migrations)

    async with factory() as session:
        result = await session.execute(
            select(PaymentTransaction).where(PaymentTransaction.payment_id == "pay-idem")
        )
        txs = result.scalars().all()
        assert len(txs) == 1  # only one transaction, not two

    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_uses_due_date_when_paid_date_is_none(_tmp_engine):
    engine = _tmp_engine
    factory = await _setup_db(engine)

    async with factory() as session:
        payment = Payment(
            id="pay-no-date",
            contractor_id="c-1",
            year=2025,
            month=5,
            amount=Decimal("100.00"),
            paid_amount=Decimal("100.00"),
            due_date=date(2025, 5, 15),
            paid_date=None,
            status="paid",
        )
        session.add(payment)
        await session.commit()

    async with engine.begin() as conn:
        await conn.run_sync(_run_migrations)

    async with factory() as session:
        result = await session.execute(
            select(PaymentTransaction).where(PaymentTransaction.payment_id == "pay-no-date")
        )
        tx = result.scalar_one()
        assert tx.paid_date == date(2025, 5, 15)  # falls back to due_date

    await engine.dispose()
