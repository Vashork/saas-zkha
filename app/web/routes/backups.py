"""
Backups route — local backup UI, manual backup creation, upload and recovery.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request, Depends, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.audit import log_admin_action
from app.backup_service import (
    BACKUP_DIR,
    MAX_UPLOAD_SIZE,
    backup_archive_absolute_path,
    cleanup_old_backups,
    copy_backup_to_remote_mount,
    create_local_backup,
    list_backup_files,
    recover_from_backup,
    safe_backup_path,
    backup_locked,
    validate_backup_archive,
)
from app.backup_settings import (
    normalize_remote_path,
    parse_bool,
    parse_frequency,
    parse_remote_type,
    parse_retention,
    parse_time,
)
from app.database import async_session_factory, get_db
from app.models import BackupHistory, Setting
from app.web.routes.auth import get_current_user
from app.web.permissions import BACKUPS_MANAGE, BACKUPS_RESTORE, has_action_permission
from app.web.template_engine import templates

logger = logging.getLogger("zhkh.backups")

router = APIRouter()

DEFAULT_RETENTION_COUNT = 10
DEFAULT_BACKUP_FREQUENCY = "manual"
DEFAULT_BACKUP_TIME = "03:00"
DEFAULT_TIMEZONE = "Europe/Moscow"
BACKUP_LOCKED_ERROR = "backup_locked"


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size_bytes} B"


def _zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %s, falling back to %s", timezone_name, DEFAULT_TIMEZONE)
        return ZoneInfo(DEFAULT_TIMEZONE)


def _format_datetime(value: datetime | None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    """Format DB/file timestamps in the configured UI timezone."""
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_zoneinfo(timezone_name)).strftime("%d.%m.%Y %H:%M:%S")


def _storage_label(storage: str) -> str:
    if storage == "synology":
        return "remote"
    return storage


async def _get_backup_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(Setting).where(Setting.key.in_([
        "backup_retention_count",
        "backup_frequency",
        "backup_time",
        "notification_timezone",
        "backup_remote_type",
        "backup_remote_path",
        "backup_keep_local_copy",
        "backup_destination_local",
        "backup_destination_remote",
    ])))
    values = {setting.key: setting.value for setting in result.scalars().all()}
    timezone_name = values.get("notification_timezone") or DEFAULT_TIMEZONE
    destination_local = parse_bool(values.get("backup_destination_local"), True)
    destination_remote = parse_bool(values.get("backup_destination_remote"), False)
    return {
        "retention_count": parse_retention(values.get("backup_retention_count")),
        "frequency": parse_frequency(values.get("backup_frequency")),
        "backup_time": parse_time(values.get("backup_time")),
        "timezone": timezone_name,
        "remote_type": parse_remote_type(values.get("backup_remote_type")),
        "remote_path": normalize_remote_path(values.get("backup_remote_path")),
        "keep_local_copy": parse_bool(values.get("backup_keep_local_copy"), True),
        "destination_local": destination_local,
        "destination_remote": destination_remote,
    }


async def _upsert_setting(db: AsyncSession, key: str, value: str, description: str) -> None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(Setting(key=key, value=value, description=description))


async def _save_backup_settings(
    db: AsyncSession,
    retention_count: int,
    frequency: str,
    backup_time: str,
    remote_type: str,
    remote_path: str,
    keep_local_copy: bool,
    destination_local: bool,
    destination_remote: bool,
) -> None:
    await _upsert_setting(db, "backup_retention_count", str(retention_count), "Сколько последних локальных архивов хранить")
    await _upsert_setting(db, "backup_frequency", frequency, "Частота автоматического локального бекапа")
    await _upsert_setting(db, "backup_time", backup_time, "Время автоматического локального бекапа")
    await _upsert_setting(db, "backup_remote_type", remote_type, "Тип удалённого бекапа: mounted share")
    await _upsert_setting(db, "backup_remote_path", remote_path, "Путь к смонтированной удалённой папке")
    await _upsert_setting(db, "backup_keep_local_copy", str(keep_local_copy).lower(), "Сохранять локальную копию при удалённом бекапе")
    await _upsert_setting(db, "backup_destination_local", str(destination_local).lower(), "Писать бекап в локальное хранилище")
    await _upsert_setting(db, "backup_destination_remote", str(destination_remote).lower(), "Копировать бекап в удалённое хранилище")
    await db.commit()


async def _reschedule_auto_backup() -> None:
    """Refresh the in-memory scheduler after backup settings are changed."""
    try:
        from app.scheduler import _schedule_backup_job
        await _schedule_backup_job()
    except Exception:
        logger.exception("Could not reschedule auto-backup after settings update")


async def _require_action_user(request: Request, db: AsyncSession, permission: str):
    current_user = await get_current_user(request, db)
    if not current_user:
        return None, RedirectResponse(url="/login", status_code=303)
    if not has_action_permission(current_user, permission):
        return current_user, RedirectResponse(url="/?denied=1", status_code=303)
    return current_user, None


async def _restore_and_reinitialize(backup_path) -> tuple[bool, str]:
    """Restore a backup and force SQLAlchemy to reopen SQLite connections."""
    from app.database import engine, init_db

    await engine.dispose()
    ok, restore_message = await run_in_threadpool(recover_from_backup, backup_path)
    await engine.dispose()
    if not ok:
        return False, restore_message

    await init_db()
    await engine.dispose()
    return True, "ok"


async def _log_backup_history(
    db: AsyncSession,
    *,
    mode: str,
    storage: str,
    status: str,
    size_bytes: int,
    file_path: str | None = None,
    error_message: str | None = None,
) -> None:
    db.add(BackupHistory(
        mode=mode,
        backup_type="full",
        size_bytes=size_bytes,
        storage=storage,
        status=status,
        file_path=file_path,
        error_message=error_message,
    ))


async def _audit_after_restore(
    *,
    actor_id: int,
    actor_username: str,
    action: str,
    entity_id: str,
    details: dict | None,
    request: Request,
) -> None:
    actor = type("AuditActor", (), {"id": actor_id, "username": actor_username})()
    async with async_session_factory() as fresh_db:
        await log_admin_action(
            fresh_db,
            actor=actor,
            action=action,
            entity_type="backup",
            entity_id=entity_id,
            details=details,
            request=request,
        )
        await fresh_db.commit()


def _remove_local_archive_if_unneeded(file_path: str) -> None:
    try:
        backup_archive_absolute_path(file_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove local archive after remote-only backup: %s", file_path)


def _locked_redirect() -> RedirectResponse:
    return RedirectResponse(url=f"/backups?error={BACKUP_LOCKED_ERROR}", status_code=303)


@router.get("/backups")
async def backups_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user, redirect = await _require_action_user(request, db, BACKUPS_MANAGE)
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
        "backup_timezone": settings["timezone"],
        "format_size": _format_size,
        "format_datetime": _format_datetime,
        "storage_label": _storage_label,
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
    backup_destination_local: str = Form(""),
    backup_destination_remote: str = Form(""),
    backup_remote_type: str = Form("smb"),
    backup_remote_path: str = Form(""),
    backup_keep_local_copy: str = Form(""),
):
    current_user, redirect = await _require_action_user(request, db, BACKUPS_MANAGE)
    if redirect:
        return redirect

    parsed_retention = parse_retention(retention_count)
    parsed_frequency = parse_frequency(frequency)
    parsed_time = parse_time(backup_time)
    destination_local = parse_bool(backup_destination_local)
    destination_remote = parse_bool(backup_destination_remote)
    remote_type = parse_remote_type(backup_remote_type)
    remote_path = normalize_remote_path(backup_remote_path)
    keep_local_copy = parse_bool(backup_keep_local_copy, True)

    if not destination_local and not destination_remote:
        return RedirectResponse(url="/backups?error=backup_destination_required", status_code=303)
    if destination_remote and not remote_path:
        return RedirectResponse(url="/backups?error=remote_path_required", status_code=303)

    await _save_backup_settings(
        db,
        parsed_retention,
        parsed_frequency,
        parsed_time,
        remote_type,
        remote_path,
        keep_local_copy,
        destination_local,
        destination_remote,
    )
    await log_admin_action(
        db,
        actor=current_user,
        action="backup_settings_update",
        entity_type="backup_settings",
        details={
            "frequency": parsed_frequency,
            "backup_time": parsed_time,
            "destination_local": destination_local,
            "destination_remote": destination_remote,
            "remote_type": remote_type,
            "keep_local_copy": keep_local_copy,
            "remote_path_configured": bool(remote_path),
        },
        request=request,
    )
    await run_in_threadpool(cleanup_old_backups, parsed_retention)
    await _reschedule_auto_backup()
    await db.commit()
    return RedirectResponse(url="/backups?success=settings_saved", status_code=303)


@router.post("/backups/create")
async def create_backup(request: Request, db: AsyncSession = Depends(get_db)):
    current_user, redirect = await _require_action_user(request, db, BACKUPS_MANAGE)
    if redirect:
        return redirect

    if backup_locked():
        return _locked_redirect()

    settings = await _get_backup_settings(db)
    retention_count = settings["retention_count"]

    try:
        file_path, size_bytes = await run_in_threadpool(create_local_backup)
        remote_ok = None
        remote_error = None
        remote_file_path = None
        remote_size = 0

        if settings["destination_remote"]:
            try:
                remote_file_path, remote_size = await run_in_threadpool(
                    copy_backup_to_remote_mount,
                    file_path,
                    settings["remote_path"],
                )
                remote_ok = True
                await _log_backup_history(
                    db,
                    mode="C",
                    storage="synology",
                    status="success",
                    size_bytes=remote_size,
                    file_path=remote_file_path,
                )
            except Exception as exc:
                logger.exception("Remote backup copy failed")
                remote_ok = False
                remote_error = str(exc)
                await _log_backup_history(
                    db,
                    mode="C",
                    storage="synology",
                    status="failed",
                    size_bytes=0,
                    error_message=remote_error,
                )

        keep_local_archive = (
            settings["destination_local"]
            or settings["keep_local_copy"]
            or not settings["destination_remote"]
            or remote_ok is False
        )
        if keep_local_archive:
            await run_in_threadpool(cleanup_old_backups, retention_count)
            await _log_backup_history(
                db,
                mode="C",
                storage="local",
                status="success",
                size_bytes=size_bytes,
                file_path=file_path,
            )
        else:
            await run_in_threadpool(_remove_local_archive_if_unneeded, file_path)

        await log_admin_action(
            db,
            actor=current_user,
            action="backup_create",
            entity_type="backup",
            entity_id=file_path,
            details={
                "local_kept": keep_local_archive,
                "remote_enabled": settings["destination_remote"],
                "remote_success": remote_ok,
                "remote_error": remote_error,
            },
            request=request,
        )
        await db.commit()
        if remote_ok is False:
            return RedirectResponse(url="/backups?success=backup_created_remote_failed", status_code=303)
        if remote_ok is True:
            return RedirectResponse(url="/backups?success=backup_created_remote", status_code=303)
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
        await log_admin_action(
            db,
            actor=current_user,
            action="backup_create_failed",
            entity_type="backup",
            details={"error": str(exc)},
            request=request,
        )
        await db.commit()
        return RedirectResponse(url="/backups?error=backup_failed", status_code=303)


@router.post("/backups/upload-restore")
async def upload_and_restore_backup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    backup_file: UploadFile = File(...),
):
    current_user, redirect = await _require_action_user(request, db, BACKUPS_RESTORE)
    if redirect:
        return redirect

    if backup_locked():
        return _locked_redirect()

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

    actor_id = current_user.id
    actor_username = current_user.username
    await db.close()
    ok, restore_message = await _restore_and_reinitialize(upload_path)
    if not ok:
        logger.warning("Uploaded backup recovery failed: %s", restore_message)
        return RedirectResponse(url="/backups?error=restore_failed", status_code=303)

    await _audit_after_restore(
        actor_id=actor_id,
        actor_username=actor_username,
        action="backup_upload_restore",
        entity_id=upload_path.name,
        details={"filename": backup_file.filename},
        request=request,
    )
    return RedirectResponse(url="/backups?success=restore_completed", status_code=303)


@router.post("/backups/restore/{filename}")
async def restore_backup(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    current_user, redirect = await _require_action_user(request, db, BACKUPS_RESTORE)
    if redirect:
        return redirect

    if backup_locked():
        return _locked_redirect()

    path = safe_backup_path(filename)
    if not path:
        return RedirectResponse(url="/backups?error=backup_not_found", status_code=303)

    actor_id = current_user.id
    actor_username = current_user.username
    await db.close()
    ok, restore_message = await _restore_and_reinitialize(path)
    if not ok:
        logger.warning("Backup recovery failed: %s", restore_message)
        return RedirectResponse(url="/backups?error=restore_failed", status_code=303)

    await _audit_after_restore(
        actor_id=actor_id,
        actor_username=actor_username,
        action="backup_restore",
        entity_id=filename,
        details=None,
        request=request,
    )
    return RedirectResponse(url="/backups?success=restore_completed", status_code=303)


@router.post("/backups/discard/{filename}")
async def discard_backup(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    current_user, redirect = await _require_action_user(request, db, BACKUPS_MANAGE)
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

    await log_admin_action(
        db,
        actor=current_user,
        action="backup_delete",
        entity_type="backup",
        entity_id=filename,
        request=request,
    )
    await db.commit()
    return RedirectResponse(url="/backups?success=backup_discarded", status_code=303)


@router.get("/backups/download/{filename}")
async def download_backup(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    _, redirect = await _require_action_user(request, db, BACKUPS_MANAGE)
    if redirect:
        return redirect

    path = safe_backup_path(filename)
    if not path:
        return RedirectResponse(url="/backups?error=backup_not_found", status_code=303)

    return FileResponse(path=path, filename=filename, media_type="application/gzip")
