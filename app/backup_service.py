"""
Backup service helpers shared by the web UI and scheduler.
"""

import logging
import shutil
import tarfile
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("zhkh.backup_service")

PROJECT_ROOT = Path("/app") if Path("/app").exists() else Path.cwd()

# --- Non-blocking lock for backup/restore operations ---
import threading

_backup_lock = threading.Lock()
_lock_owner_thread: int | None = None
LOCKED_MESSAGE = "Другая операция backup/restore уже выполняется"


def acquire_backup_lock() -> bool:
    """Attempt to acquire the backup lock (non-blocking). Returns True if acquired."""
    global _lock_owner_thread
    acquired = _backup_lock.acquire(blocking=False)
    if acquired:
        _lock_owner_thread = threading.get_ident()
    return acquired


def release_backup_lock() -> None:
    """Release the backup lock. No-op if not held by this thread."""
    global _lock_owner_thread
    if _lock_owner_thread != threading.get_ident():
        return
    try:
        _backup_lock.release()
    except RuntimeError:
        pass
    _lock_owner_thread = None


def backup_locked() -> bool:
    """Check whether the backup lock is currently held."""
    return _backup_lock.locked()


def _reset_lock_for_tests() -> None:
    """Force-release the lock — only for tests."""
    global _lock_owner_thread
    _lock_owner_thread = None
    try:
        _backup_lock.release()
    except RuntimeError:
        pass
BACKUP_DIR = PROJECT_ROOT / "backups"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_RETENTION_COUNT = 10
DEFAULT_BACKUP_FREQUENCY = "manual"
DEFAULT_BACKUP_TIME = "03:00"
MAX_UPLOAD_SIZE = 500 * 1024 * 1024


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Python-version-safe Path.is_relative_to replacement."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _forbidden_remote_backup_dirs() -> list[Path]:
    """Directories that must never be used as a mounted remote backup target."""
    return [
        DATA_DIR,
        DATA_DIR / "uploads",
        BACKUP_DIR,
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "docker",
        PROJECT_ROOT / "scripts",
    ]


def _validate_remote_backup_target_dir(target_dir: Path) -> Path:
    """Reject remote backup targets that point back into app/data/local storage.

    Remote backup is intended for an already-mounted external directory. This
    guard prevents accidental configuration such as /app/data, /app/backups or
    /app/data/uploads, which could create recursive backups, leak receipts via
    uploads, or fill the application volume.
    """
    resolved_target = target_dir.resolve(strict=False)
    for forbidden in _forbidden_remote_backup_dirs():
        resolved_forbidden = forbidden.resolve(strict=False)
        if resolved_target == resolved_forbidden or _is_relative_to(resolved_target, resolved_forbidden):
            raise ValueError(
                f"Путь mounted share не должен указывать внутрь локальных данных приложения: {resolved_target}"
            )
    return resolved_target


def backup_archive_absolute_path(relative_path: str | Path) -> Path:
    """Resolve a backup archive path returned by create_local_backup()."""
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def create_local_backup() -> tuple[str, int]:
    """Create a tar.gz archive of data/ and return relative path and size."""
    if not acquire_backup_lock():
        raise RuntimeError(LOCKED_MESSAGE)
    try:
        return _create_local_backup_impl()
    finally:
        release_backup_lock()


def _create_local_backup_impl() -> tuple[str, int]:
    """Internal implementation that assumes the lock is already held."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"zhkh-data-backup-{timestamp}.tar.gz"

    with tarfile.open(backup_path, "w:gz") as archive:
        if DATA_DIR.exists():
            archive.add(DATA_DIR, arcname="data")
    return f"backups/{backup_path.name}", backup_path.stat().st_size


def copy_backup_to_remote_mount(local_backup_path: str | Path, remote_dir: str) -> tuple[str, int]:
    """Copy a local backup archive to an already-mounted remote directory.

    This first remote-backup phase deliberately avoids storing SMB/SFTP secrets in
    the app. Mount the remote destination outside the app/container, then point
    remote_dir to that mounted path.
    """
    if not remote_dir or not remote_dir.strip():
        raise ValueError("Remote backup path is empty")

    source = backup_archive_absolute_path(local_backup_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Local backup archive not found: {source}")

    target_dir = Path(remote_dir.strip())
    if not target_dir.is_absolute():
        target_dir = PROJECT_ROOT / target_dir
    target_dir = _validate_remote_backup_target_dir(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / source.name
    tmp_target = target_dir / f".{source.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copy2(source, tmp_target)
        tmp_target.replace(target)
    finally:
        tmp_target.unlink(missing_ok=True)

    return str(target), target.stat().st_size


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
    return backup_archive_absolute_path(relative_path)


def recover_from_backup(path: Path) -> tuple[bool, str]:
    """Recover data/ from a validated backup archive and roll back on failure."""
    if not acquire_backup_lock():
        return False, LOCKED_MESSAGE

    try:
        valid, message = validate_backup_archive(path)
        if not valid:
            return False, message

        safety_backup_path: Path | None = None
        try:
            # Safety backup uses the internal implementation (lock already held)
            safety_backup_rel, _ = _create_local_backup_impl()
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
    finally:
        release_backup_lock()


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
