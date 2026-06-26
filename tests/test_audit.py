"""Audit log helper tests."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.audit import log_admin_action
from app.database import Base
from app.models import AuditLog, User
from app.utils import hash_password


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/backups/create",
            "headers": [],
            "query_string": b"",
            "client": ("192.0.2.10", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_empty_receive,
    )


@pytest.mark.asyncio
async def test_log_admin_action_writes_audit_row(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        actor = User(username="admin", password_hash=hash_password("password123"), role="admin", is_active=True)
        session.add(actor)
        await session.flush()

        await log_admin_action(
            session,
            actor=actor,
            action="backup_create",
            entity_type="backup",
            entity_id="backups/example.tar.gz",
            details={"remote_success": True},
            request=_request(),
        )
        await session.commit()

        audit = await session.scalar(select(AuditLog))
        assert audit is not None
        assert audit.actor_user_id == actor.id
        assert audit.actor_username == "admin"
        assert audit.action == "backup_create"
        assert audit.entity_type == "backup"
        assert audit.entity_id == "backups/example.tar.gz"
        assert audit.client_ip == "192.0.2.10"
        assert json.loads(audit.details) == {"remote_success": True}

    await engine.dispose()
