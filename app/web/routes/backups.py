"""
Backups route — local backup UI, manual backup creation, upload and recovery.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.backup_service import (
    BACKUP_DIR,
    MAX_UPLOAD_SIZE,
    cleanup_old_backups,
    create_local_backup,
    list_backup_files,
    recover_from_backup,
    safe_backup_path,
    validate_backup_archive,
)
from app.database import get_db, engine
from app.models import BackupHistory, Setting
from app.web.routes.auth import get_current_user

logger = logging.getLogger("zhkh.backups")

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

DEFAULT_RETENTION_COUNT = 10
DEFAULT_BACKUP_FREQUENCY = "manual"
DEFAULT_BACKUP_TIME = "03:00"


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size_bytes} B"


def _parse_retention(value: str | None) -> int:
    try:
        retention_count = int(value or DEFAULT_RETENTION_COUNT)
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_COUNT
    if retention_count < 1:
        return 1
    if retention_count > 100:
        return 100
    return retention_count


def _parse_frequency(value: str | None) -> str:
    if value in {"manual", "daily", "weekly", "monthly"}:
        return value
    return DEFAULT_BACKUP_FREQUENCY


def _parse_time(value: str | None) -> str:
    value = value or DEFAULT_BACKUP_TIME
    try:
        hour, minute = value.split(":")
        hour_i = int(hour)
        minute_i = int(minute)
    except (ValueError, AttributeError):
        return DEFAULT_BACKUP_TIME
    if not (0 <= hour_i <= 23 and 0 <= minute_i <= 59):
        return DEFAULT_BACKUP_TIME
    return f"{hour_i:02d}:{minute_i:02d}"


async def _get_backup_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(Setting).where(Setting.key.in_([
        "backup_retention_count",
        "backup_frequency",
        "backup_time",
    ])))
    values = {setting.key: setting.value for setting in result.scalars().all()}
    return {
        "retention_count": _parse_retention(values.get("backup_retention_count")),
        "frequency": _parse_frequency(values.get("backup_frequency")),
        "backup_time": _parse_time(values.get("backup_time")),
    }


async def _upsert_setting(db: AsyncSession, key: str, value: str, description: str) -> None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(Setting(key=key, value=value, description=description))


async def _save_backup_settings(db: AsyncSession, retention_count: int, frequency: str, backup_time: str) -> None:
    await _upsert_setting(db, "backup_retention_count", str(retention_count), "Сколько последних локальных архивов хранить")
    await _upsert_setting(db, "backup_frequency", frequency, "Частота автоматического локального бекапа")
    await _upsert_setting(db, "backup_time", backup_time, "Время автоматического локального бекапа")
    await db.commit()


async def _require_admin(request: Request, db: AsyncSession):
    current_user = await get_current_user(request, db)
    if not current_user:
        return None, RedirectResponse(url="/login", status_code=303)
    if current_user.role != "admin":
        return current_user, RedirectResponse(url="/?denied=1", status_code=303)
    return current_user, None


@router.get("/backups")
async def backups_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    result = await db.execute(select(BackupHistory).order_by(BackupHistory.created_at.desc()))
    history = result.scalars().all()
    settings = await _get_backup_settings(db)

    return templates.TemplateResponse("backups.html", {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "history": history,
        "backup_files": list_backup_files(),
        "backup_settings": settings,
        "format_size": _format_size,
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
    })


@router.post("/backups/settings")
async def save_backup_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    retention_count: str = Form("10"),
    frequency: str = Form("manual"),
    backup_time: str = Form("03:00"),
):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    parsed_retention = _parse_retention(retention_count)
    parsed_frequency = _parse_frequency(frequency)
    parsed_time = _parse_time(backup_time)
    await _save_backup_settings(db, parsed_retention, parsed_frequency, parsed_time)
    await run_in_threadpool(cleanup_old_backups, parsed_retention)
    return RedirectResponse(url="/backups?success=settings_saved", status_code=303)


@router.post("/backups/create")
async def create_backup(request: Request, db: AsyncSession = Depends(get_db)):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    settings = await _get_backup_settings(db)
    retention_count = settings["retention_count"]

    try:
        file_path, size_bytes = await run_in_threadpool(create_local_backup)
        await run_in_threadpool(cleanup_old_backups, retention_count)
        db.add(BackupHistory(
            mode="C",
            backup_type="full",
            size_bytes=size_bytes,
            storage="local",
            status="success",
            file_path=file_path,
        ))
        await db.commit()
        return RedirectResponse(url="/backups?success=backup_created", status_code=303)
    except Exception as exc:
        logger.exception("Backup creation failed")
        db.add(BackupHistory(
            mode="C",
            backup_type="full",
            size_bytes=0,
            storage="local",
            status="failed",
            error_message=str(exc),
            file_path=None,
        ))
        await db.commit()
        return RedirectResponse(url="/backups?error=backup_failed", status_code=303)


@router.post("/backups/upload-restore")
async def upload_and_restore_backup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    backup_file: UploadFile = File(...),
):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    if not backup_file.filename or not backup_file.filename.endswith(".tar.gz"):
        return RedirectResponse(url="/backups?error=backup_invalid", status_code=303)

    content = await backup_file.read()
    if not content or len(content) > MAX_UPLOAD_SIZE:
        return RedirectResponse(url="/backups?error=backup_invalid", status_code=303)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    upload_path = BACKUP_DIR / f"zhkh-data-backup-uploaded-{timestamp}.tar.gz"
    upload_path.write_bytes(content)

    valid, message = await run_in_threadpool(validate_backup_archive, upload_path)
    if not valid:
        upload_path.unlink(missing_ok=True)
        logger.warning("Uploaded backup validation failed: %s", message)
        return RedirectResponse(url="/backups?error=backup_invalid", status_code=303)

    await db.close()
    await engine.dispose()
    ok, restore_message = await run_in_threadpool(recover_from_backup, upload_path)
    if not ok:
        logger.warning("Uploaded backup recovery failed: %s", restore_message)
        return RedirectResponse(url="/backups?error=restore_failed", status_code=303)

    return RedirectResponse(url="/backups?success=restore_completed", status_code=303)


@router.post("/backups/restore/{filename}")
async def restore_backup(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    path = safe_backup_path(filename)
    if not path:
        return RedirectResponse(url="/backups?error=backup_not_found", status_code=303)

    await db.close()
    await engine.dispose()
    ok, restore_message = await run_in_threadpool(recover_from_backup, path)
    if not ok:
        logger.warning("Backup recovery failed: %s", restore_message)
        return RedirectResponse(url="/backups?error=restore_failed", status_code=303)

    return RedirectResponse(url="/backups?success=restore_completed", status_code=303)


@router.post("/backups/discard/{filename}")
async def discard_backup(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    path = safe_backup_path(filename)
    if not path:
        return RedirectResponse(url="/backups?error=backup_not_found", status_code=303)

    try:
        path.unlink()
    except OSError as exc:
        logger.warning("Backup discard failed: %s", exc)
        return RedirectResponse(url="/backups?error=backup_discard_failed", status_code=303)

    return RedirectResponse(url="/backups?success=backup_discarded", status_code=303)


@router.get("/backups/download/{filename}")
async def download_backup(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    path = safe_backup_path(filename)
    if not path:
        return RedirectResponse(url="/backups?error=backup_not_found", status_code=303)

    return FileResponse(path=path, filename=filename, media_type="application/gzip")
