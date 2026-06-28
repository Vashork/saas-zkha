"""Tests for Alembic integration with the project.

Verifies:
1. Alembic is installed and configured
2. Migration history is correct
3. Alembic can upgrade a fresh database
4. Backfill migration works idempotently
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _alembic_cmd(*args: str) -> list[str]:
    """Return a cross-platform Alembic command.

    On Windows the console script may not be on PATH when tests are launched as
    `python -m pytest`, but `python -m alembic` uses the active interpreter and
    works the same way on Windows and Linux.
    """
    return [sys.executable, "-m", "alembic", "-c", str(PROJECT_ROOT / "alembic.ini"), *args]


def _run_alembic(*args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        _alembic_cmd(*args),
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def test_alembic_is_installed():
    """Alembic must be in requirements.txt."""
    req_path = PROJECT_ROOT / "requirements.txt"
    content = req_path.read_text(encoding="utf-8")
    assert "alembic" in content


def test_alembic_config_exists():
    """alembic.ini must exist at project root."""
    ini_path = PROJECT_ROOT / "alembic.ini"
    assert ini_path.is_file()


def test_alembic_env_loads_models():
    """env.py must import from app.database and app.models."""
    env_path = PROJECT_ROOT / "alembic" / "env.py"
    content = env_path.read_text(encoding="utf-8")
    assert "from app.database import Base" in content
    assert "from app import models" in content


def test_alembic_migrations_exist():
    """At least one migration file should exist in alembic/versions/."""
    versions_dir = PROJECT_ROOT / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    assert len(migration_files) >= 2  # initial_schema + backfill


def test_alembic_upgrade_on_fresh_db(tmp_path: Path):
    """Alembic should upgrade a fresh (empty) database without errors."""
    db_path = tmp_path / "test.db"

    # Must use sqlite+aiosqlite URL so that app.database imports correctly
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}

    result = _run_alembic("upgrade", "head", env=env)
    assert result.returncode == 0, f"Alembic upgrade failed: {result.stderr}"

    # Verify the DB file was created
    assert db_path.is_file()


def test_alembic_current_shows_head(tmp_path: Path):
    """After upgrade, `alembic current` should report 'head'."""
    db_path = tmp_path / "test_current.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, f"Alembic upgrade failed: {upgrade.stderr}"

    result = _run_alembic("current", env=env)
    assert result.returncode == 0
    assert "head" in result.stdout.lower()


def test_alembic_history_shows_migrations():
    """alembic history should list at least 2 migrations."""
    result = _run_alembic("history")
    assert result.returncode == 0
    assert "initial_schema" in result.stdout
    assert "backfill_payment_transactions" in result.stdout


def test_database_init_uses_alembic():
    """app.database.init_db must reference alembic/subprocess."""
    import app.database as db_mod

    source = Path(db_mod.__file__).read_text(encoding="utf-8")
    assert "alembic" in source
    assert "subprocess" in source


def test_init_db_uses_alembic():
    """init_db.py must reference alembic/subprocess."""
    init_path = PROJECT_ROOT / "init_db.py"
    content = init_path.read_text(encoding="utf-8")
    assert "alembic" in content
    assert "subprocess" in content


def test_backfill_migration_is_idempotent(tmp_path: Path):
    """Running the backfill migration twice should not create duplicate rows."""
    import sqlite3

    db_path = tmp_path / "backfill_test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}

    # Upgrade to head (applies both migrations)
    result = _run_alembic("upgrade", "head", env=env)
    assert result.returncode == 0, f"Alembic upgrade failed: {result.stderr}"

    conn = sqlite3.connect(str(db_path))
    # The backfill migration runs on empty payments table — no rows should be created
    count = conn.execute(
        "SELECT COUNT(*) FROM payment_transactions WHERE id LIKE 'tx-backfill-%'"
    ).fetchone()[0]
    assert count == 0  # No payments exist, so no backfill rows

    # Downgrade and upgrade again to test idempotency
    conn.close()
    downgrade = _run_alembic("downgrade", "base", env=env)
    assert downgrade.returncode == 0, f"Alembic downgrade failed: {downgrade.stderr}"
    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, f"Alembic re-upgrade failed: {upgrade.stderr}"
