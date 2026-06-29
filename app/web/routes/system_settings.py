"""Additional system settings routes."""

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_admin_action
from app.config import get_settings
from app.database import get_db
from app.models import Setting
from app.timezone_settings import normalize_timezone
from app.web.routes.auth import get_current_user

logger = logging.getLogger("zhkh.system_settings")

router = APIRouter()


async def _upsert_setting(db: AsyncSession, key: str, value: str, description: str) -> None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(Setting(key=key, value=value, description=description))


async def _reschedule_scheduler_after_timezone_change() -> None:
    """Refresh in-memory jobs that depend on the DB notification timezone."""
    try:
        from app.scheduler import _reschedule_notification_jobs, _schedule_backup_job

        await _reschedule_notification_jobs()
        await _schedule_backup_job()
    except Exception:
        logger.exception("Could not reschedule jobs after notification timezone update")


@router.post("/settings/timezone")
async def save_notification_timezone(
    request: Request,
    db: AsyncSession = Depends(get_db),
    notification_timezone: str = Form("Europe/Moscow"),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    if current_user.role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    configured_default = get_settings().NOTIFICATION_TIMEZONE
    normalized_timezone = normalize_timezone(notification_timezone, configured_default)
    await _upsert_setting(
        db,
        "notification_timezone",
        normalized_timezone,
        "Часовой пояс уведомлений и отображения времени бекапов",
    )
    await log_admin_action(
        db,
        actor=current_user,
        action="notification_timezone_update",
        entity_type="settings",
        details={"notification_timezone": normalized_timezone},
        request=request,
    )
    await db.commit()
    await _reschedule_scheduler_after_timezone_change()
    return RedirectResponse(url="/settings?success=Часовой+пояс+сохранён", status_code=303)
