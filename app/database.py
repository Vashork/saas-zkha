"""
Async database engine and session management (SQLite + aiosqlite).
"""

import logging
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
    """Create all tables and run migrations."""
    from app import models  # noqa: F401 — import to register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_migrations)


def _run_migrations(conn):
    """Apply incremental migrations to an existing database."""
    result = conn.execute(text("PRAGMA table_info(users)"))
    columns = [row[1] for row in result.fetchall()]

    if "page_permissions" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN page_permissions TEXT"))
        logger.info("Migration: added page_permissions to users")

    if "is_active" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1"))
        logger.info("Migration: added is_active to users")

    _backfill_legacy_payment_transactions(conn)


def _backfill_legacy_payment_transactions(conn) -> None:
    """Create child transactions for legacy paid payments, idempotently.

    Docker startup runs init_db.py, but web lifespan and restore reinitialization use
    app.database.init_db(). Keep this backfill here too so restored legacy backups are
    normalized before the app starts serving requests again.
    """
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
    logger.info("Migration: ensured legacy paid payments have payment_transactions")
