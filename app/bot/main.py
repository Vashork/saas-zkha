"""
Telegram bot — main entry point. Runs aiogram 3.x poller.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter

from app.config import get_settings
from app.bot.handlers import paid_handler, start_handler, contractors_handler
from app.bot.interactive import (
    ReceiptFlow,
    cancel_handler,
    receipt_amount_handler,
    receipt_confirm_handler,
    receipt_contractor_handler,
    receipt_period_handler,
    receipt_start_handler,
)

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

    dp.message.register(start_handler, Command("start"))
    dp.message.register(contractors_handler, Command("contractors"))
    dp.message.register(cancel_handler, Command("cancel"))

    dp.message.register(receipt_contractor_handler, StateFilter(ReceiptFlow.contractor))
    dp.message.register(receipt_amount_handler, StateFilter(ReceiptFlow.amount))
    dp.message.register(receipt_period_handler, StateFilter(ReceiptFlow.period))
    dp.message.register(receipt_confirm_handler, StateFilter(ReceiptFlow.confirm))

    dp.message.register(
        paid_handler,
        lambda m: m.text and "#оплачено" in m.text.lower(),
    )
    dp.message.register(
        receipt_start_handler,
        lambda m: (m.document or m.photo) and not (m.text and "#оплачено" in m.text.lower()),
    )

    logger.info("Starting bot polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
