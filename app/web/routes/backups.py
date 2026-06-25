"""
Backups route — local backup UI and manual backup creation.
"""

import logging
import tarfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.models import BackupHistory
from app.web.routes.auth import get_current_user

logger = logging.getLogger("zhkh.backups")

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

PROJECT_ROOT = Path("/app") if Path("/app").exists() else Path.cwd()
BACKUP_DIR = PROJECT_ROOT / "backups"
DATA_DIR = PROJECT_ROOT / "data"


def _create_local_backup() -> tuple[str, int]:
    """Create a data-only tar.gz backup and return relative path and size."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"zhkh-data-backup-{timestamp}.tar.gz"
    backup_path = BACKUP_DIR / filename

    with tarfile.open(backup_path, "w:gz") as tar:
        if DATA_DIR.exists():
            tar.add(DATA_DIR, arcname="data")

    return f"backups/{filename}", backup_path.stat().st_size


def _list_backup_files() -> list[dict]:
    """List local backup archive files for the UI."""
    if not BACKUP_DIR.exists():
        return []

    files = []
    for path in sorted(BACKUP_DIR.glob("zhkh-data-backup-*.tar.gz"), reverse=True):
        stat = path.stat()
        files.append({
            "name": path.name,
            "download_url": f"/backups/download/{path.name}",
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime),
        })
    return files


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size_bytes} B"


def _safe_backup_path(filename: str) -> Path | None:
    """Return a backup path only for expected archive filenames."""
    if "/" in filename or ".." in filename:
        return None
    if not filename.startswith("zhkh-data-backup-") or not filename.endswith(".tar.gz"):
        return None
    path = BACKUP_DIR / filename
    if not path.exists() or not path.is_file():
        return None
    return path


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

    return templates.TemplateResponse("backups.html", {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "history": history,
        "backup_files": _list_backup_files(),
        "format_size": _format_size,
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
    })


@router.post("/backups/create")
async def create_backup(request: Request, db: AsyncSession = Depends(get_db)):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    try:
        file_path, size_bytes = await run_in_threadpool(_create_local_backup)
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


@router.get("/backups/download/{filename}")
async def download_backup(filename: str, request: Request, db: AsyncSession = Depends(get_db)):
    _, redirect = await _require_admin(request, db)
    if redirect:
        return redirect

    path = _safe_backup_path(filename)
    if not path:
        return RedirectResponse(url="/backups?error=backup_not_found", status_code=303)

    return FileResponse(path=path, filename=filename, media_type="application/gzip")
