"""
Async database engine and session management (SQLite + aiosqlite).

The app keeps a legacy schema-bootstrap path for existing SQLite deployments,
then registers that schema with Alembic so future migrations can run safely.
"""

import logging
import subprocess
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

INITIAL_ALEMBIC_REVISION = "b3b26935f1bf"


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
    """Initialize or migrate the database.

    Existing installations were created by SQLAlchemy create_all() plus ad-hoc
    migrations. Running Alembic's initial schema revision directly against those
    databases would fail with "table already exists". To make startup safe, we
    first ensure the legacy schema shape exists, then stamp existing schemas to
    the initial Alembic revision and upgrade to head.
    """
    await _ensure_sqlite_parent_dir()
    await _legacy_init()
    await _ensure_alembic_head()


async def _ensure_sqlite_parent_dir() -> None:
    db_path = settings.DATABASE_URL
    if not db_path.startswith("sqlite"):
        return
    path_str = db_path.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
    if path_str:
        Path(path_str).parent.resolve().mkdir(parents=True, exist_ok=True)


async def _legacy_init():
    """Create missing tables and run idempotent legacy migrations."""
    from app import models  # noqa: F401 — import to register models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_legacy_migrations)


async def _ensure_alembic_head() -> None:
    """Register the current schema with Alembic and run remaining revisions."""
    project_root = Path(__file__).resolve().parent.parent
    if not (project_root / "alembic.ini").exists():
        logger.warning("alembic.ini not found, using legacy DB init only")
        return

    try:
        if not await _has_alembic_version_table():
            _run_alembic(project_root, "stamp", INITIAL_ALEMBIC_REVISION)
        _run_alembic(project_root, "upgrade", "head")
        logger.info("Alembic migrations applied successfully")
    except FileNotFoundError:
        logger.warning("alembic command not found, using legacy DB init only")
    except RuntimeError as exc:
        logger.exception("Alembic migration failed")
        raise exc


async def _has_alembic_version_table() -> bool:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table("alembic_version"))


def _run_alembic(project_root: Path, *args: str) -> None:
    result = subprocess.run(
        ["alembic", "-c", str(project_root / "alembic.ini"), *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Alembic {' '.join(args)} failed: stdout={result.stdout!r} stderr={result.stderr!r}"
        )


def _run_legacy_migrations(conn):
    """Legacy incremental migrations kept for existing SQLite databases.

    New structural changes should be added as Alembic revision files, but this
    path remains necessary so old ad-hoc databases can be safely stamped into
    Alembic without the initial schema migration trying to recreate tables.
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
    _ensure_telegram_message_log(conn)
    _ensure_telegram_outbound_message_log(conn)


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


def _ensure_telegram_message_log(conn) -> None:
    """Create Telegram inbound message log for legacy SQLite databases."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS telegram_message_log (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            telegram_user_id INTEGER,
            username VARCHAR,
            first_name VARCHAR,
            last_name VARCHAR,
            chat_id INTEGER,
            message_type VARCHAR NOT NULL DEFAULT 'message',
            text TEXT,
            is_allowed BOOLEAN NOT NULL DEFAULT 0,
            is_admin BOOLEAN NOT NULL DEFAULT 0
        )
    """))


def _ensure_telegram_outbound_message_log(conn) -> None:
    """Create Telegram outbound reply/edit log for legacy SQLite databases."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS telegram_outbound_message_log (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            inbound_message_id INTEGER,
            actor_user_id INTEGER,
            chat_id INTEGER NOT NULL,
            telegram_message_id INTEGER,
            text TEXT NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'pending',
            error_message TEXT,
            is_edited BOOLEAN NOT NULL DEFAULT 0,
            CONSTRAINT ck_telegram_outbound_status CHECK (status IN ('pending', 'sent', 'failed', 'edited')),
            FOREIGN KEY(inbound_message_id) REFERENCES telegram_message_log (id),
            FOREIGN KEY(actor_user_id) REFERENCES users (id)
        )
    """))
