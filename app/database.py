"""
Async database engine and session management (SQLite + aiosqlite).

Alembic handles schema migrations. init_db() runs Alembic upgrade head
on startup so the DB is always up-to-date.
"""

import logging
import subprocess
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


logger = logging.getLogger("zhkh.database")


async def init_db():
    """Run Alembic migrations to bring the database up to date.

    Falls back to legacy schema creation if alembic_version table
    does not exist yet (first ever run on a brand-new DB).
    """
    from app import models  # noqa: F401 — import to register models

    # Ensure data directory exists
    db_path = settings.DATABASE_URL
    if db_path.startswith("sqlite"):
        # Extract path from sqlite:///... or sqlite+aiosqlite:///...
        path_str = db_path.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
        data_dir = Path(path_str).parent.resolve()
        data_dir.mkdir(parents=True, exist_ok=True)

    # Run Alembic upgrade to head
    project_root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["alembic", "-c", str(project_root / "alembic.ini"), "upgrade", "head"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Alembic upgrade output: %s", result.stderr)
            # If alembic_version doesn't exist yet, stamp and upgrade
            _maybe_stamp_and_upgrade(project_root)
        else:
            logger.info("Alembic migrations applied successfully")
    except FileNotFoundError:
        logger.warning("alembic command not found, falling back to legacy init")
        await _legacy_init()


def _maybe_stamp_and_upgrade(project_root: Path):
    """If the DB has no alembic_version, stamp to the initial migration and upgrade."""
    try:
        subprocess.run(
            ["alembic", "-c", str(project_root / "alembic.ini"), "stamp", "base"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["alembic", "-c", str(project_root / "alembic.ini"), "upgrade", "head"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        logger.info("Alembic stamped to base and upgraded to head")
    except FileNotFoundError:
        pass


async def _legacy_init():
    """Fallback: create all tables and run ad-hoc migrations (legacy path)."""
    from app import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_legacy_migrations)


def _run_legacy_migrations(conn):
    """Legacy incremental migrations — kept for fallback only.

    New migrations should be added as Alembic revision files in alembic/versions/.
    """
    result = conn.execute(text("PRAGMA table_info(users)"))
    columns = [row[1] for row in result.fetchall()]

    if "page_permissions" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN page_permissions TEXT"))
        logger.info("Legacy migration: added page_permissions to users")

    if "is_active" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1"))
        logger.info("Legacy migration: added is_active to users")

    _backfill_legacy_payment_transactions(conn)


def _backfill_legacy_payment_transactions(conn) -> None:
    """Create child transactions for legacy paid payments, idempotently."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS payment_transactions (
            id VARCHAR NOT NULL PRIMARY KEY,
            payment_id VARCHAR NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            paid_date DATE NOT NULL,
            receipt_file VARCHAR,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_payment_transaction_amount_positive CHECK (amount > 0),
            FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE CASCADE
        )
    """))

    conn.execute(text("""
        INSERT INTO payment_transactions (id, payment_id, amount, paid_date, receipt_file, notes)
        SELECT
            'tx-backfill-' || p.id,
            p.id,
            p.paid_amount,
            COALESCE(p.paid_date, p.due_date),
            p.receipt_file,
            'Backfilled from legacy payment fields'
        FROM payments p
        WHERE p.paid_amount IS NOT NULL
          AND p.paid_amount > 0
          AND NOT EXISTS (
              SELECT 1 FROM payment_transactions t WHERE t.payment_id = p.id
          )
    """))
    logger.info("Legacy migration: ensured legacy paid payments have payment_transactions")
