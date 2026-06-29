"""Alembic environment configuration for saas-zkha.

Supports both online (async) and offline modes for SQLite + aiosqlite.
Uses synchronous engine for migrations (Alembic limitation) but reads
the DATABASE_URL from app configuration to stay consistent.
"""

import sys
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, event, Column, Integer, String, Numeric, DateTime, Text, ForeignKey, MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import DeclarativeBase

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so that `app.*` imports work
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Load target metadata — import models inside run_migrations_* so that
# app.database is not imported at module level (which would create an async
# engine with a potentially incompatible DATABASE_URL).
# ---------------------------------------------------------------------------
def _import_models():
    """Import Base and models lazily to avoid async engine creation at import time."""
    from app.database import Base  # noqa: F402
    from app import models  # noqa: F401, F402  # register all model classes
    return Base.metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_url() -> str:
    """Return the DATABASE_URL from environment, falling back to alembic.ini."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    ini_url = config.get_main_option("sqlalchemy.url")
    return ini_url


def _sync_url_for_sqlite(async_url: str) -> str:
    """Convert sqlite+aiosqlite:///... → sqlite:///... for synchronous Alembic."""
    if async_url.startswith("sqlite+aiosqlite://"):
        return async_url.replace("sqlite+aiosqlite://", "sqlite://")
    return async_url


# ---------------------------------------------------------------------------
# SQLite WAL mode
# ---------------------------------------------------------------------------
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


# ===================================================================
# Offline mode
# ===================================================================
def run_migrations_offline() -> None:
    target_metadata = _import_models()
    url = _sync_url_for_sqlite(get_url())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ===================================================================
# Online mode
# ===================================================================
def run_migrations_online() -> None:
    target_metadata = _import_models()
    sync_url = _sync_url_for_sqlite(get_url())

    connectable = create_engine(sync_url, poolclass=StaticPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
