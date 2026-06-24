"""
Bot notifications — sends Telegram messages about backups, scheduler events, etc.
"""

import logging
from aiogram import Bot
from app.config import get_settings

logger = logging.getLogger("zhkh.bot.notifications")


async def send_notification(chat_id: int, text: str):
    """Send a notification to a specific Telegram user."""
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("Bot token not set, cannot send notification")
        return

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        logger.info("Notification sent to %s", chat_id)
    except Exception as e:
        logger.error("Failed to send notification: %s", e)
    finally:
        await bot.session.close()
