"""
Telegram bot — main entry point. Runs aiogram 3.x poller.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.bot.handlers import paid_handler, start_handler, contractors_handler, set_bot_instance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zhkh.bot")


async def main():
    settings = get_settings()
    token = settings.TELEGRAM_BOT_TOKEN

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot will not run")
        while True:
            await asyncio.sleep(3600)
        return

    bot = Bot(token=token)
    dp = Dispatcher()

    set_bot_instance(bot)

    # Register handlers
    dp.message.register(start_handler, Command("start"))
    dp.message.register(contractors_handler, Command("contractors"))
    dp.message.register(paid_handler, lambda m: "#оплачено" in (m.text or "").lower())

    logger.info("Starting bot polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
