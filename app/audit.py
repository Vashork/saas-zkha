"""Audit logging helpers for admin actions."""

import json
import logging
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

logger = logging.getLogger("zhkh.audit")


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _safe_details(details: dict[str, Any] | None) -> str | None:
    if not details:
        return None
    try:
        return json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return json.dumps({"unserializable": True}, ensure_ascii=False)


async def log_admin_action(
    db: AsyncSession,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Append one audit record without exposing secrets."""
    try:
        db.add(AuditLog(
            actor_user_id=getattr(actor, "id", None),
            actor_username=getattr(actor, "username", None),
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=_safe_details(details),
            client_ip=_client_ip(request),
        ))
    except Exception:
        logger.exception("Could not enqueue audit log entry")
