"""Telegram bot access-control helpers."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy import select

from app.database import async_session_factory
from app.models import TelegramMessageLog

logger = logging.getLogger("zhkh.bot.security")


class TelegramAllowlistMiddleware(BaseMiddleware):
    """Log inbound messages and silently ignore users outside the allowlist."""

    def __init__(self, allowed_user_ids: set[int], admin_user_id: int | None = None) -> None:
        self.allowed_user_ids = set(allowed_user_ids)
        self.admin_user_id = admin_user_id
        self._warned_empty_allowlist = False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        is_allowed = bool(self.allowed_user_ids) and user_id in self.allowed_user_ids
        is_admin = self.admin_user_id is not None and user_id == self.admin_user_id

        if isinstance(event, Message):
            await log_telegram_message(event, is_allowed=is_allowed, is_admin=is_admin)

        if not self.allowed_user_ids:
            if not self._warned_empty_allowlist:
                logger.warning(
                    "Telegram allowlist is empty; ignoring all bot messages. "
                    "Set TELEGRAM_ALLOWED_USER_IDS or TELEGRAM_ADMIN_ID."
                )
                self._warned_empty_allowlist = True
            return None

        if not is_allowed:
            logger.info("Ignoring Telegram message from unauthorized user id=%s", user_id)
            return None

        return await handler(event, data)


def register_telegram_allowlist(
    dispatcher,
    allowed_user_ids: set[int],
    admin_user_id: int | None = None,
) -> None:
    """Register access-control middleware for all message handlers."""
    dispatcher.message.middleware(TelegramAllowlistMiddleware(allowed_user_ids, admin_user_id))


def is_allowed_message(message: Message, allowed_user_ids: set[int]) -> bool:
    """Small helper for unit tests and future non-message handlers."""
    user_id = message.from_user.id if message.from_user else None
    return bool(allowed_user_ids) and user_id in allowed_user_ids


def _message_text(message: Message) -> str | None:
    text = message.text or message.caption
    if text:
        return text[:4000]
    if message.document:
        return f"[document] {message.document.file_name or message.document.file_id}"
    if message.photo:
        return "[photo]"
    return None


async def log_telegram_message(
    message: Message,
    *,
    is_allowed: bool,
    is_admin: bool,
) -> None:
    """Persist one inbound Telegram message for admin inspection."""
    user = message.from_user
    try:
        async with async_session_factory() as session:
            session.add(TelegramMessageLog(
                telegram_user_id=user.id if user else None,
                username=user.username if user else None,
                first_name=user.first_name if user else None,
                last_name=user.last_name if user else None,
                chat_id=message.chat.id if message.chat else None,
                message_type=getattr(message, "content_type", "message"),
                text=_message_text(message),
                is_allowed=is_allowed,
                is_admin=is_admin,
            ))
            await session.commit()
    except Exception:
        logger.exception("Could not write Telegram message log")


async def recent_telegram_messages(limit: int = 20) -> list[TelegramMessageLog]:
    """Return newest Telegram message log entries."""
    safe_limit = min(max(limit, 1), 50)
    async with async_session_factory() as session:
        result = await session.execute(
            select(TelegramMessageLog)
            .order_by(TelegramMessageLog.id.desc())
            .limit(safe_limit)
        )
        return list(result.scalars().all())
