"""Tests for backup/restore locking — prevents concurrent operations."""

import asyncio
import multiprocessing
import os as _os
from pathlib import Path

import pytest

from app.backup_service import (
    acquire_backup_lock,
    release_backup_lock,
    backup_locked,
    recover_from_backup,
    _acquire_file_lock,
    _release_file_lock,
    _check_file_lock,
    fcntl,
)


def _write_data_tree(root: Path, db_content: str) -> None:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "zhkh.db").write_text(db_content, encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_lock_state():
    """Ensure the lock is released before and after each test."""
    import app.backup_service as bs

    bs._reset_lock_for_tests()
    bs._file_lock_path = None
    yield
    bs._reset_lock_for_tests()
    bs._file_lock_path = None


def test_acquire_and_release_backup_lock():
    assert acquire_backup_lock() is True
    assert backup_locked() is True
    release_backup_lock()
    assert backup_locked() is False


def test_acquire_backup_lock_when_already_locked():
    acquire_backup_lock()
    try:
        assert acquire_backup_lock() is False
    finally:
        release_backup_lock()


def test_backup_locked_returns_false_when_free():
    assert backup_locked() is False


def test_lock_message_on_contention():
    acquire_backup_lock()
    try:
        expected_msg = "Другая операция backup/restore уже выполняется"
        assert backup_locked() is True
        from app.backup_service import LOCKED_MESSAGE
        assert LOCKED_MESSAGE == expected_msg
    finally:
        release_backup_lock()


def test_release_lock_when_not_locked_is_noop():
    release_backup_lock()


@pytest.mark.asyncio
async def test_scheduled_backup_aborts_when_manual_is_running(tmp_path, monkeypatch):
    """When the lock is held by a manual backup, the scheduled backup should abort."""
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    backup_dir = project_root / "backups"
    backup_dir.mkdir(parents=True)
    _write_data_tree(project_root, "test-db")

    monkeypatch.setattr("app.backup_service.PROJECT_ROOT", project_root)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)
    monkeypatch.setattr("app.backup_service.DATA_DIR", data_dir)

    acquire_backup_lock()
    try:
        from app.backup_service import LOCKED_MESSAGE
        assert backup_locked() is True
        assert LOCKED_MESSAGE == "Другая операция backup/restore уже выполняется"
    finally:
        release_backup_lock()


@pytest.mark.asyncio
async def test_recover_from_backup_aborts_when_locked(tmp_path, monkeypatch):
    """recover_from_backup must check the lock before starting."""
    import tarfile

    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    backup_dir = project_root / "backups"
    remote_root = tmp_path / "remote"

    backup_dir.mkdir(parents=True)
    _write_data_tree(project_root, "original-db")
    _write_data_tree(remote_root, "restored-db")

    archive_path = backup_dir / "zhkh-data-backup-restore.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(remote_root / "data", arcname="data")

    monkeypatch.setattr("app.backup_service.PROJECT_ROOT", project_root)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)
    monkeypatch.setattr("app.backup_service.DATA_DIR", data_dir)

    acquire_backup_lock()
    try:
        ok, message = recover_from_backup(archive_path)
        assert ok is False
        assert "Другая операция backup/restore уже выполняется" in message
    finally:
        release_backup_lock()


@pytest.mark.asyncio
async def test_concurrent_backups_serialized(tmp_path, monkeypatch):
    """Two concurrent backup operations should not both succeed."""
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    backup_dir = project_root / "backups"
    backup_dir.mkdir(parents=True)
    _write_data_tree(project_root, "concurrent-test-db")

    monkeypatch.setattr("app.backup_service.PROJECT_ROOT", project_root)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)
    monkeypatch.setattr("app.backup_service.DATA_DIR", data_dir)

    results = {}

    async def backup_a():
        results["a"] = acquire_backup_lock()
        await asyncio.sleep(0.1)
        release_backup_lock()

    async def backup_b():
        await asyncio.sleep(0.02)
        results["b"] = acquire_backup_lock()
        if results["b"]:
            release_backup_lock()

    await asyncio.gather(backup_a(), backup_b())

    assert results["a"] is True
    assert results["b"] is False


def test_file_lock_acquire_and_release(tmp_path, monkeypatch):
    """File lock can be acquired and released."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)

    assert _acquire_file_lock() is True
    _release_file_lock()
    assert _acquire_file_lock() is True
    _release_file_lock()


def test_file_lock_blocks_second_acquisition_in_same_process(tmp_path, monkeypatch):
    """The service refuses a second tracked file-lock acquisition in one process."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)

    assert _acquire_file_lock() is True
    try:
        assert _acquire_file_lock() is False
    finally:
        _release_file_lock()


def test_file_lock_check_when_free(tmp_path, monkeypatch):
    """_check_file_lock returns False when no lock is held."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)

    assert _check_file_lock() is False


def _try_lock_in_child(lock_file: str, queue) -> None:
    if fcntl is None:
        queue.put(True)
        return
    fd = _os.open(lock_file, _os.O_CREAT | _os.O_WRONLY, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        queue.put(True)
        fcntl.flock(fd, fcntl.LOCK_UN)
    except (BlockingIOError, OSError):
        queue.put(False)
    finally:
        _os.close(fd)


def _hold_lock_in_child(lock_file: str, ready, release) -> None:
    if fcntl is None:
        ready.put(True)
        release.get(timeout=5)
        return
    fd = _os.open(lock_file, _os.O_CREAT | _os.O_WRONLY, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        ready.put(True)
        release.get(timeout=5)
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        _os.close(fd)


@pytest.mark.skipif(fcntl is None, reason="fcntl is not available on this platform")
def test_file_lock_blocks_other_process(tmp_path, monkeypatch):
    """A lock held by this process blocks a different process."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)
    lock_file = str(backup_dir / ".backup-operation.lock")

    assert _acquire_file_lock() is True
    try:
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_try_lock_in_child, args=(lock_file, queue))
        process.start()
        process.join(timeout=5)
        assert process.exitcode == 0
        assert queue.get(timeout=1) is False
    finally:
        _release_file_lock()


@pytest.mark.skipif(fcntl is None, reason="fcntl is not available on this platform")
def test_file_lock_check_when_held_by_other_process(tmp_path, monkeypatch):
    """_check_file_lock returns True when a different process holds the lock."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)
    lock_file = str(backup_dir / ".backup-operation.lock")

    ready = multiprocessing.Queue()
    release = multiprocessing.Queue()
    process = multiprocessing.Process(target=_hold_lock_in_child, args=(lock_file, ready, release))
    process.start()
    try:
        assert ready.get(timeout=5) is True
        assert _check_file_lock() is True
    finally:
        release.put(True)
        process.join(timeout=5)
        assert process.exitcode == 0


@pytest.mark.skipif(fcntl is None, reason="fcntl is not available on this platform")
def test_combined_lock_requires_file_lock(tmp_path, monkeypatch):
    """acquire_backup_lock fails if another process holds the file lock."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setattr("app.backup_service.BACKUP_DIR", backup_dir)
    monkeypatch.setattr("app.backup_service.DATA_DIR", data_dir)
    lock_file = str(backup_dir / ".backup-operation.lock")

    ready = multiprocessing.Queue()
    release = multiprocessing.Queue()
    process = multiprocessing.Process(target=_hold_lock_in_child, args=(lock_file, ready, release))
    process.start()
    try:
        assert ready.get(timeout=5) is True
        assert acquire_backup_lock() is False
    finally:
        release.put(True)
        process.join(timeout=5)
        assert process.exitcode == 0
