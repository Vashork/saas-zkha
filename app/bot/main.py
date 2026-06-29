"""
Telegram bot — main entry point. Runs aiogram 3.x poller.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import BotCommand

from app.config import get_settings
from app.bot.security import register_telegram_allowlist
from app.bot.handlers import (
    balance_handler,
    contractors_handler,
    help_handler,
    paid_handler,
    start_handler,
    tglog_handler,
)
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


def _message_text(message) -> str:
    return message.text or message.caption or ""


def _telegram_admin_id(raw: str) -> int | None:
    try:
        return int(raw.strip()) if raw and raw.strip() else None
    except ValueError:
        return None


async def main():
    settings = get_settings()
    token = settings.TELEGRAM_BOT_TOKEN

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot will not run")
        while True:
            await asyncio.sleep(3600)
        return

    bot = Bot(token=token)
    await bot.set_my_commands([
        BotCommand(command="help", description="Все команды и подсказка по оплате"),
        BotCommand(command="balance", description="Остатки по платежам за текущий месяц"),
        BotCommand(command="contractors", description="Список подрядчиков и тегов"),
        BotCommand(command="tglog", description="Журнал сообщений, только для Telegram-админа"),
    ])
    dp = Dispatcher()
    admin_user_id = _telegram_admin_id(settings.TELEGRAM_ADMIN_ID)
    register_telegram_allowlist(dp, settings.TELEGRAM_ALLOWED_USER_IDS, admin_user_id)

    dp.message.register(start_handler, Command("start"))
    dp.message.register(help_handler, Command("help"))
    dp.message.register(balance_handler, Command("balance"))
    dp.message.register(contractors_handler, Command("contractors"))
    dp.message.register(tglog_handler, Command("tglog"))
    dp.message.register(cancel_handler, Command("cancel"))

    dp.message.register(receipt_contractor_handler, StateFilter(ReceiptFlow.contractor))
    dp.message.register(receipt_amount_handler, StateFilter(ReceiptFlow.amount))
    dp.message.register(receipt_period_handler, StateFilter(ReceiptFlow.period))
    dp.message.register(receipt_confirm_handler, StateFilter(ReceiptFlow.confirm))

    dp.message.register(
        paid_handler,
        lambda m: "#оплачено" in _message_text(m).lower(),
    )
    dp.message.register(
        receipt_start_handler,
        lambda m: (m.document or m.photo) and "#оплачено" not in _message_text(m).lower(),
    )

    logger.info("Starting bot polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
