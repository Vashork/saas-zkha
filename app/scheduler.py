"""
APScheduler — auto-generation of monthly payments and payment status checks.
"""

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.database import async_session_factory
from app.models import Contractor, Payment

logger = logging.getLogger("zhkh.scheduler")
scheduler = AsyncIOScheduler()


def _month_name(month: int) -> str:
    names = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    return names.get(month, str(month))


async def generate_monthly_payments():
    """
    Create pending payments for all active contractors for the current month.

    The generation must be idempotent per contractor, not per month. If one
    payment already exists for the month, the scheduler still has to create
    missing rows for other active contractors.
    """
    settings = get_settings()
    if not settings.GENERATION_ENABLED:
        return

    today = date.today()
    year, month = today.year, today.month

    async with async_session_factory() as session:
        result = await session.execute(select(Contractor).where(Contractor.is_active == True))
        contractors = result.scalars().all()

        created = 0
        skipped = 0
        for contractor in contractors:
            existing_payment_id = await session.scalar(
                select(Payment.id).where(
                    Payment.contractor_id == contractor.id,
                    Payment.year == year,
                    Payment.month == month,
                )
            )
            if existing_payment_id:
                skipped += 1
                continue

            due_day = min(contractor.due_day, 28)
            due_date = date(year, month, due_day)
            amount = contractor.fixed_amount if contractor.payment_type == "fixed" else None

            payment = Payment(
                id=f"pay-{year}{month:02d}-{contractor.id}",
                contractor_id=contractor.id,
                year=year,
                month=month,
                amount=amount,
                due_date=due_date,
                status="pending",
            )
            session.add(payment)
            created += 1

        await session.commit()
        logger.info(
            "Monthly payment generation for %s %s: created %s, skipped %s existing rows",
            _month_name(month),
            year,
            created,
            skipped,
        )


async def check_notifications():
    """Update overdue payments and log due-soon counts."""
    today = date.today()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Payment)
            .options(joinedload(Payment.contractor))
            .where(Payment.status == "pending")
        )
        payments = result.scalars().all()

        overdue = [p for p in payments if p.due_date < today]
        urgent = [p for p in payments if 0 <= (p.due_date - today).days <= 5]

        for payment in overdue:
            payment.status = "overdue"
            logger.warning("Overdue: contractor %s, due %s", payment.contractor_id, payment.due_date)

        if urgent or overdue:
            await session.commit()
            logger.info("Payment status check: %s due soon, %s overdue", len(urgent), len(overdue))


def start_scheduler():
    """Start the APScheduler with payment generation and status-check jobs."""
    settings = get_settings()

    gen_hour, gen_min = map(int, settings.GENERATION_TIME.split(":"))
    notif_hour, notif_min = map(int, settings.NOTIFICATION_TIME.split(":"))

    # Run once on application startup as an idempotent repair step for missing
    # current-month payments. The function itself skips existing contractor rows.
    scheduler.add_job(
        generate_monthly_payments,
        "date",
        id="generate_payments_on_start",
        replace_existing=True,
    )

    scheduler.add_job(
        generate_monthly_payments,
        "cron",
        day=settings.GENERATION_DAY,
        hour=gen_hour,
        minute=gen_min,
        timezone=settings.NOTIFICATION_TIMEZONE,
        id="generate_payments",
        replace_existing=True,
    )

    scheduler.add_job(
        check_notifications,
        "cron",
        hour=notif_hour,
        minute=notif_min,
        timezone=settings.NOTIFICATION_TIMEZONE,
        id="check_notifications",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: generation %s:%s day %s, status checks %s:%s",
        gen_hour,
        gen_min,
        settings.GENERATION_DAY,
        notif_hour,
        notif_min,
    )


def stop_scheduler():
    """Stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
