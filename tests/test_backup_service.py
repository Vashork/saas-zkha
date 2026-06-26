"""Backup service regression tests."""

import tarfile
from pathlib import Path

import pytest

from app import backup_service


def _write_data_tree(root: Path, db_content: str, extra_file: str | None = None) -> None:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "zhkh.db").write_text(db_content, encoding="utf-8")
    if extra_file:
        (data_dir / extra_file).write_text("extra", encoding="utf-8")


def _make_backup_archive(path: Path, source_root: Path) -> None:
    with tarfile.open(path, "w:gz") as archive:
        archive.add(source_root / "data", arcname="data")


def test_recover_from_backup_success_replaces_data(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    backup_dir = project_root / "backups"
    current_root = tmp_path / "current"
    restore_root = tmp_path / "restore"

    _write_data_tree(current_root, "original-db", "old.txt")
    _write_data_tree(restore_root, "restored-db", "new.txt")
    backup_dir.mkdir(parents=True)
    archive_path = backup_dir / "zhkh-data-backup-restore.tar.gz"
    _make_backup_archive(archive_path, restore_root)

    monkeypatch.setattr(backup_service, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(backup_service, "DATA_DIR", current_root / "data")

    ok, message = backup_service.recover_from_backup(archive_path)

    assert ok is True
    assert message == "ok"
    assert (current_root / "data" / "zhkh.db").read_text(encoding="utf-8") == "restored-db"
    assert not (current_root / "data" / "old.txt").exists()
    assert (current_root / "data" / "new.txt").exists()


def test_recover_from_backup_rolls_back_original_data_after_copy_failure(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    backup_dir = project_root / "backups"
    current_root = tmp_path / "current"
    restore_root = tmp_path / "restore"

    _write_data_tree(current_root, "original-db", "old.txt")
    _write_data_tree(restore_root, "restored-db", "new.txt")
    backup_dir.mkdir(parents=True)
    archive_path = backup_dir / "zhkh-data-backup-restore.tar.gz"
    _make_backup_archive(archive_path, restore_root)

    monkeypatch.setattr(backup_service, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(backup_service, "DATA_DIR", current_root / "data")

    original_copy = backup_service._copy_directory_contents
    calls = {"count": 0}

    def flaky_copy(source_dir: Path, target_dir: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated copy failure after data clear")
        original_copy(source_dir, target_dir)

    monkeypatch.setattr(backup_service, "_copy_directory_contents", flaky_copy)

    ok, message = backup_service.recover_from_backup(archive_path)

    assert ok is False
    assert "исходные данные возвращены" in message
    assert calls["count"] == 2
    assert (current_root / "data" / "zhkh.db").read_text(encoding="utf-8") == "original-db"
    assert (current_root / "data" / "old.txt").exists()
    assert not (current_root / "data" / "new.txt").exists()


def test_validate_backup_archive_rejects_path_traversal(tmp_path):
    archive_path = tmp_path / "bad.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("bad", encoding="utf-8")

    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(payload, arcname="data/../escape.txt")

    ok, message = backup_service.validate_backup_archive(archive_path)

    assert ok is False
    assert "небезопасные пути" in message


def test_copy_backup_to_remote_mount_copies_archive_atomically(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    local_dir = project_root / "backups"
    remote_dir = tmp_path / "remote"
    local_dir.mkdir(parents=True)
    local_backup = local_dir / "zhkh-data-backup-test.tar.gz"
    local_backup.write_bytes(b"backup-content")

    monkeypatch.setattr(backup_service, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", local_dir)
    monkeypatch.setattr(backup_service, "DATA_DIR", project_root / "data")

    remote_path, size = backup_service.copy_backup_to_remote_mount(
        "backups/zhkh-data-backup-test.tar.gz",
        str(remote_dir),
    )

    assert size == len(b"backup-content")
    assert Path(remote_path) == remote_dir / local_backup.name
    assert Path(remote_path).read_bytes() == b"backup-content"
    assert not list(remote_dir.glob("*.tmp"))


def test_copy_backup_to_remote_mount_rejects_empty_path(tmp_path):
    local_backup = tmp_path / "zhkh-data-backup-test.tar.gz"
    local_backup.write_bytes(b"backup-content")

    with pytest.raises(ValueError):
        backup_service.copy_backup_to_remote_mount(local_backup, "")


def test_copy_backup_to_remote_mount_rejects_app_data_target(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    local_dir = project_root / "backups"
    data_dir = project_root / "data"
    local_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    local_backup = local_dir / "zhkh-data-backup-test.tar.gz"
    local_backup.write_bytes(b"backup-content")

    monkeypatch.setattr(backup_service, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", local_dir)
    monkeypatch.setattr(backup_service, "DATA_DIR", data_dir)

    with pytest.raises(ValueError, match="Unsafe remote backup path"):
        backup_service.copy_backup_to_remote_mount(
            "backups/zhkh-data-backup-test.tar.gz",
            str(data_dir / "uploads" / "remote-copy"),
        )


def test_copy_backup_to_remote_mount_rejects_local_backup_target(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    local_dir = project_root / "backups"
    local_dir.mkdir(parents=True)
    local_backup = local_dir / "zhkh-data-backup-test.tar.gz"
    local_backup.write_bytes(b"backup-content")

    monkeypatch.setattr(backup_service, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", local_dir)
    monkeypatch.setattr(backup_service, "DATA_DIR", project_root / "data")

    with pytest.raises(ValueError, match="Unsafe remote backup path"):
        backup_service.copy_backup_to_remote_mount(
            "backups/zhkh-data-backup-test.tar.gz",
            str(local_dir / "remote-copy"),
        )
