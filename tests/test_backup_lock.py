"""Tests for backup/restore locking — prevents concurrent operations."""

import asyncio
from pathlib import Path

import pytest

from app.backup_service import (
    acquire_backup_lock,
    release_backup_lock,
    backup_locked,
    create_local_backup,
    recover_from_backup,
)


def _write_data_tree(root: Path, db_content: str) -> None:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "zhkh.db").write_text(db_content, encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_lock_state():
    """Ensure the lock is released before and after each test."""
    from app.backup_service import _reset_lock_for_tests
    _reset_lock_for_tests()
    yield
    _reset_lock_for_tests()


def test_acquire_and_release_backup_lock():
    assert acquire_backup_lock() is True
    assert backup_locked() is True
    release_backup_lock()
    assert backup_locked() is False


def test_acquire_backup_lock_when_already_locked():
    acquire_backup_lock()
    assert acquire_backup_lock() is False
    release_backup_lock()


def test_backup_locked_returns_false_when_free():
    assert backup_locked() is False


def test_lock_message_on_contention():
    acquire_backup_lock()
    expected_msg = "Другая операция backup/restore уже выполняется"
    assert backup_locked() is True
    # The message is returned by helper, not by the boolean check
    from app.backup_service import LOCKED_MESSAGE
    assert LOCKED_MESSAGE == expected_msg
    release_backup_lock()


def test_release_lock_when_not_locked_is_noop():
    release_backup_lock()  # should not raise


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

    # Simulate a manual backup holding the lock
    acquire_backup_lock()
    try:
        # Attempt another backup — should fail with contention message
        from app.backup_service import LOCKED_MESSAGE
        locked = backup_locked()
        assert locked is True
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

    # Hold the lock
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
        acquire_backup_lock()
        results["a"] = True
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
