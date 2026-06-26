"""
Backup service helpers shared by the web UI and scheduler.
"""

import logging
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("zhkh.backup_service")

PROJECT_ROOT = Path("/app") if Path("/app").exists() else Path.cwd()
BACKUP_DIR = PROJECT_ROOT / "backups"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_RETENTION_COUNT = 10
DEFAULT_BACKUP_FREQUENCY = "manual"
DEFAULT_BACKUP_TIME = "03:00"
MAX_UPLOAD_SIZE = 500 * 1024 * 1024


def create_local_backup() -> tuple[str, int]:
    """Create a tar.gz archive of data/ and return relative path and size."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"zhkh-data-backup-{timestamp}.tar.gz"

    with tarfile.open(backup_path, "w:gz") as archive:
        if DATA_DIR.exists():
            archive.add(DATA_DIR, arcname="data")

    return f"backups/{backup_path.name}", backup_path.stat().st_size


def list_backup_files() -> list[dict]:
    """List local backup archives for the UI."""
    if not BACKUP_DIR.exists():
        return []

    files = []
    for path in sorted(BACKUP_DIR.glob("zhkh-data-backup-*.tar.gz"), reverse=True):
        stat = path.stat()
        files.append({
            "name": path.name,
            "download_url": f"/backups/download/{path.name}",
            "restore_url": f"/backups/restore/{path.name}",
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime),
        })
    return files


def cleanup_old_backups(retention_count: int) -> int:
    """Keep only the newest N local backup archives."""
    if retention_count < 1 or not BACKUP_DIR.exists():
        return 0

    files = sorted(
        BACKUP_DIR.glob("zhkh-data-backup-*.tar.gz"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    deleted = 0
    for path in files[retention_count:]:
        try:
            path.unlink()
            deleted += 1
        except OSError:
            logger.warning("Could not remove old backup: %s", path)
    return deleted


def safe_backup_path(filename: str) -> Path | None:
    """Return a local archive path only for expected filenames."""
    if "/" in filename or ".." in filename:
        return None
    if not filename.startswith("zhkh-data-backup-") or not filename.endswith(".tar.gz"):
        return None
    path = BACKUP_DIR / filename
    if not path.exists() or not path.is_file():
        return None
    return path


def validate_backup_archive(path: Path) -> tuple[bool, str]:
    """Validate archive structure before recovery."""
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
    except tarfile.TarError:
        return False, "Архив повреждён или не является tar.gz"

    if not members:
        return False, "Архив пустой"

    names = []
    for member in members:
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            return False, "В архиве есть небезопасные пути"
        if not member.name.startswith("data/") and member.name != "data":
            return False, "Архив должен содержать только каталог data/"
        if member.issym() or member.islnk():
            return False, "Архив не должен содержать ссылки"
        names.append(member.name)

    if "data/zhkh.db" not in names:
        return False, "В архиве нет data/zhkh.db"

    return True, "ok"


def _safe_unpack_data_dir(archive_path: Path, target_root: Path) -> None:
    """Unpack only regular files and directories under data/."""
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            member_path = Path(member.name)
            target_path = target_root / member_path
            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            with source, target_path.open("wb") as output:
                shutil.copyfileobj(source, output)


def _clear_directory_contents(path: Path) -> None:
    """
    Clear a directory without deleting the directory itself.

    /app/data is normally a Docker volume mount point. Removing that mount point
    with shutil.rmtree('/app/data') fails with 'Device or resource busy', so
    restore must delete only children inside the directory.
    """
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_directory_contents(source_dir: Path, target_dir: Path) -> None:
    """Copy source_dir children into target_dir without replacing target_dir itself."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        target = target_dir / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def _restore_data_from_archive(path: Path) -> None:
    """Replace DATA_DIR contents from a validated archive without creating a safety backup."""
    with tempfile.TemporaryDirectory() as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        _safe_unpack_data_dir(path, tmp_dir)
        recovered_data = tmp_dir / "data"
        if not (recovered_data / "zhkh.db").exists():
            raise FileNotFoundError("После распаковки не найден data/zhkh.db")

        _clear_directory_contents(DATA_DIR)
        _copy_directory_contents(recovered_data, DATA_DIR)


def _safety_backup_absolute_path(relative_path: str) -> Path:
    """Resolve the relative path returned by create_local_backup()."""
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def recover_from_backup(path: Path) -> tuple[bool, str]:
    """Recover data/ from a validated backup archive and roll back on failure."""
    valid, message = validate_backup_archive(path)
    if not valid:
        return False, message

    safety_backup_path: Path | None = None
    try:
        safety_backup_rel, _ = create_local_backup()
        safety_backup_path = _safety_backup_absolute_path(safety_backup_rel)
        _restore_data_from_archive(path)
    except OSError as exc:
        logger.exception("Backup recovery filesystem error")
        rollback_ok, rollback_message = _rollback_from_safety_backup(safety_backup_path)
        if rollback_ok:
            return False, f"Ошибка файловой системы при восстановлении, исходные данные возвращены: {exc}"
        return False, f"Ошибка файловой системы при восстановлении: {exc}. Rollback failed: {rollback_message}"
    except Exception as exc:
        logger.exception("Backup recovery failed")
        rollback_ok, rollback_message = _rollback_from_safety_backup(safety_backup_path)
        if rollback_ok:
            return False, f"Ошибка восстановления, исходные данные возвращены: {exc}"
        return False, f"Ошибка восстановления: {exc}. Rollback failed: {rollback_message}"

    return True, "ok"


def _rollback_from_safety_backup(safety_backup_path: Path | None) -> tuple[bool, str]:
    """Best-effort restore of original data after a failed recovery attempt."""
    if safety_backup_path is None:
        return False, "safety backup was not created"
    if not safety_backup_path.exists():
        return False, f"safety backup not found: {safety_backup_path}"

    try:
        _restore_data_from_archive(safety_backup_path)
    except Exception as exc:
        logger.exception("Rollback from safety backup failed")
        return False, str(exc)

    logger.warning("Restored original data from safety backup after failed recovery: %s", safety_backup_path)
    return True, "ok"
