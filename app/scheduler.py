"""
APScheduler — auto-generation of monthly payments and payment status checks.
"""

import logging
import asyncio
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.database import async_session_factory
from app.models import Contractor, Payment, BackupHistory, Setting
from app.backup_service import (
    backup_archive_absolute_path,
    cleanup_old_backups,
    copy_backup_to_remote_mount,
    create_local_backup,
    backup_locked,
)
from app.backup_settings import (
    normalize_remote_path,
    parse_bool,
    parse_frequency,
    parse_remote_type,
    parse_retention,
    parse_time,
)
from app.timezone_settings import normalize_timezone

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


def _schedule_notification_jobs(notification_timezone: str) -> None:
    """Add or replace recurring payment generation/status jobs in one timezone."""
    settings = get_settings()
    gen_hour, gen_min = map(int, settings.GENERATION_TIME.split(":"))
    notif_hour, notif_min = map(int, settings.NOTIFICATION_TIME.split(":"))
    timezone_name = normalize_timezone(notification_timezone, settings.NOTIFICATION_TIMEZONE)

    scheduler.add_job(
        generate_monthly_payments,
        "cron",
        day=settings.GENERATION_DAY,
        hour=gen_hour,
        minute=gen_min,
        timezone=timezone_name,
        id="generate_payments",
        replace_existing=True,
    )

    scheduler.add_job(
        check_notifications,
        "cron",
        hour=notif_hour,
        minute=notif_min,
        timezone=timezone_name,
        id="check_notifications",
        replace_existing=True,
    )

    logger.info(
        "Notification scheduler jobs set to timezone %s: generation %s:%s day %s, status checks %s:%s",
        timezone_name,
        gen_hour,
        gen_min,
        settings.GENERATION_DAY,
        notif_hour,
        notif_min,
    )


async def _load_notification_timezone() -> str:
    """Read the DB notification timezone, falling back to env/default config."""
    configured_default = get_settings().NOTIFICATION_TIMEZONE
    async with async_session_factory() as session:
        value = await session.scalar(
            select(Setting.value).where(Setting.key == "notification_timezone")
        )
    return normalize_timezone(value, configured_default)


async def _reschedule_notification_jobs() -> None:
    """Refresh recurring notification-related jobs after timezone setting changes."""
    timezone_name = await _load_notification_timezone()
    _schedule_notification_jobs(timezone_name)


def start_scheduler():
    """Start the APScheduler with payment generation and status-check jobs."""
    settings = get_settings()

    scheduler.add_job(
        generate_monthly_payments,
        "date",
        id="generate_payments_on_start",
        replace_existing=True,
    )
    _schedule_notification_jobs(settings.NOTIFICATION_TIMEZONE)

    scheduler.start()
    logger.info("Scheduler started")

    asyncio.create_task(_reschedule_notification_jobs())
    asyncio.create_task(_schedule_backup_job())


def stop_scheduler():
    """Stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown()


# ---------------------------------------------------------------------------
# Helpers for reading backup settings from the database
# ---------------------------------------------------------------------------


async def _load_backup_settings() -> dict:
    """Read backup settings from DB."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Setting).where(Setting.key.in_(
                [
                    "backup_retention_count",
                    "backup_frequency",
                    "backup_time",
                    "backup_remote_type",
                    "backup_remote_path",
                    "backup_keep_local_copy",
                    "backup_destination_local",
                    "backup_destination_remote",
                    "notification_timezone",
                ]
            ))
        )
        values = {s.key: s.value for s in result.scalars().all()}

    configured_default = get_settings().NOTIFICATION_TIMEZONE
    return {
        "retention_count": parse_retention(values.get("backup_retention_count")),
        "frequency": parse_frequency(values.get("backup_frequency")),
        "backup_time": parse_time(values.get("backup_time")),
        "remote_type": parse_remote_type(values.get("backup_remote_type")),
        "remote_path": normalize_remote_path(values.get("backup_remote_path")),
        "keep_local_copy": parse_bool(values.get("backup_keep_local_copy"), True),
        "destination_local": parse_bool(values.get("backup_destination_local"), True),
        "destination_remote": parse_bool(values.get("backup_destination_remote"), False),
        "timezone": normalize_timezone(values.get("notification_timezone"), configured_default),
    }


# ---------------------------------------------------------------------------
# Auto-backup job
# ---------------------------------------------------------------------------

async def _add_backup_history(
    *,
    mode: str,
    storage: str,
    status: str,
    size_bytes: int,
    file_path: str | None = None,
    error_message: str | None = None,
) -> None:
    async with async_session_factory() as session:
        session.add(BackupHistory(
            mode=mode,
            backup_type="full",
            size_bytes=size_bytes,
            storage=storage,
            status=status,
            file_path=file_path,
            error_message=error_message,
        ))
        await session.commit()


def _remove_local_archive_if_unneeded(file_path: str) -> None:
    try:
        backup_archive_absolute_path(file_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove local archive after scheduled remote-only backup: %s", file_path)


async def scheduled_backup_job():
    """Create a backup according to local/remote destination settings and log the result."""
    settings = await _load_backup_settings()
    retention = settings["retention_count"]

    # Skip if a manual backup/restore is currently running
    if backup_locked():
        logger.info("Skipping scheduled backup: another backup/restore operation is running")
        return

    try:
        file_path, size_bytes = await asyncio.to_thread(create_local_backup)
        remote_ok = None

        if settings["destination_remote"]:
            try:
                remote_file_path, remote_size = await asyncio.to_thread(
                    copy_backup_to_remote_mount,
                    file_path,
                    settings["remote_path"],
                )
                remote_ok = True
                await _add_backup_history(
                    mode="A",
                    storage="synology",
                    status="success",
                    size_bytes=remote_size,
                    file_path=remote_file_path,
                )
                logger.info("Scheduled remote backup created: %s (%d bytes)", remote_file_path, remote_size)
            except Exception as exc:
                remote_ok = False
                logger.exception("Scheduled remote backup failed")
                await _add_backup_history(
                    mode="A",
                    storage="synology",
                    status="failed",
                    size_bytes=0,
                    error_message=str(exc),
                )

        keep_local_archive = (
            settings["destination_local"]
            or settings["keep_local_copy"]
            or not settings["destination_remote"]
            or remote_ok is False
        )
        if keep_local_archive:
            await asyncio.to_thread(cleanup_old_backups, retention)
            await _add_backup_history(
                mode="A",
                storage="local",
                status="success",
                size_bytes=size_bytes,
                file_path=file_path,
            )
            logger.info("Scheduled local backup created: %s (%d bytes)", file_path, size_bytes)
        else:
            await asyncio.to_thread(_remove_local_archive_if_unneeded, file_path)

    except Exception as exc:
        logger.exception("Scheduled backup failed")
        try:
            await _add_backup_history(
                mode="A",
                storage="local",
                status="failed",
                size_bytes=0,
                error_message=str(exc),
            )
        except Exception:
            logger.exception("Failed to log backup failure")


# ---------------------------------------------------------------------------
# Cron-expression builder for backup frequency
# ---------------------------------------------------------------------------


def _build_cron_kwargs(backup_time: str) -> dict:
    h, m = map(int, backup_time.split(":"))
    cron: dict = {}
    cron["hour"] = h
    cron["minute"] = m
    return cron


async def _schedule_backup_job():
    """Read settings from DB and add / replace the auto-backup cron job."""
    settings = await _load_backup_settings()
    freq = settings["frequency"]

    try:
        scheduler.remove_job("auto_backup")
    except Exception:
        pass

    if freq == "manual":
        logger.info("Auto-backup: disabled (manual mode)")
        return

    cron_kw = _build_cron_kwargs(settings["backup_time"])
    if freq == "weekly":
        cron_kw["day_of_week"] = "mon"
    elif freq == "monthly":
        cron_kw["day"] = "1"

    scheduler.add_job(
        scheduled_backup_job,
        "cron",
        id="auto_backup",
        replace_existing=True,
        timezone=settings["timezone"],
        **cron_kw,
    )
    logger.info("Auto-backup scheduled: %s at %s %s", freq, settings["backup_time"], settings["timezone"])
