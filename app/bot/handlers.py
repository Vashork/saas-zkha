"""
Telegram bot handlers — command and message handlers.
"""

import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from aiogram.types import Message, FSInputFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models import Contractor, Payment
from app.bot.parsers import parse_payment_message
from app.utils import month_name, get_upload_path, is_allowed_file

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")


async def start_handler(message: Message):
    """Handle /start command."""
    await message.answer(
        "🏠 Добро пожаловать в систему учета ЖКХ!\n\n"
        "💡 Как зафиксировать оплату:\n"
        "Перешлите чек и напишите:\n"
        "<code>#оплачено #мосэнергосбыт #сумма:3200</code>\n\n"
        "📋 Команды:\n"
        "/contractors — список подрядчиков\n"
        "/start — это сообщение"
    )


async def contractors_handler(message: Message):
    """Handle /contractors command — list active contractors."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Contractor).where(Contractor.is_active == True)
        )
        contractors = result.scalars().all()

    if not contractors:
        await message.answer("📋 Подрядчиков пока нет. Добавьте через веб-интерфейс.")
        return

    lines = [f"📋 Подрядчики:\n"]
    for c in contractors:
        amt = f"{c.fixed_amount} ₽" if c.payment_type == "fixed" and c.fixed_amount else "по чеку"
        lines.append(f"• {c.name} (<code>#{c.slug}</code>) — {amt}, срок: {c.due_day}-е число")

    lines.append("\n💡 Для оплаты: <code>#оплачено #[slug] #сумма:X</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def paid_handler(message: Message):
    """Handle payment confirmation message."""
    parsed = parse_payment_message(message.text)
    if not parsed:
        await message.answer("❌ Неверный формат. Используйте: <code>#оплачено #[slug] #сумма:X</code>", parse_mode="HTML")
        return

    # Find contractor by slug
    async with async_session_factory() as session:
        result = await session.execute(
            select(Contractor).where(Contractor.slug == parsed.slug)
        )
        contractor = result.scalar_one_or_none()

        if not contractor:
            await message.answer(f"❌ Подрядчик «#{parsed.slug}» не найден.\nПопробуйте: /contractors")
            return

        # Check payment_type requires amount
        if contractor.payment_type == "variable" and not parsed.amount:
            await message.answer(f"❌ Укажите сумму: <code>#сумма:[число]</code>", parse_mode="HTML")
            return

        # Find pending payment for current month
        today = date.today()
        result = await session.execute(
            select(Payment).where(
                Payment.contractor_id == contractor.id,
                Payment.year == today.year,
                Payment.month == today.month,
                Payment.status == "pending",
            )
        )
        payment = result.scalar_one_or_none()

        if not payment:
            await message.answer(
                f"❌ Не найдена неоплаченная запись за {contractor.name} "
                f"за {month_name(today.month)} {today.year}"
            )
            return

        # Save receipt file if attached
        receipt_path = None
        if message.document or message.photo:
            file = message.document or message.photo[-1]
            file_obj = await bot.get_file(file.file_id)
            ext = ".pdf" if message.document and message.document.mime_subtype == "pdf" else ".jpg"
            upload_dir = get_upload_path(today.year, today.month, UPLOAD_DIR)
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(upload_dir, filename)
            await file_obj.download_to_file(filepath)
            receipt_path = f"{today.year}/{today.month:02d}/{filename}"

        # Update payment
        amount = parsed.amount if parsed.amount else contractor.fixed_amount
        payment.paid_amount = amount
        payment.paid_date = today
        payment.status = "paid"
        payment.receipt_file = receipt_path

        await session.flush()

    emoji = "✅"
    await message.answer(
        f"{emoji} Оплата <b>{contractor.name}</b> зафиксирована!\n"
        f"💰 Сумма: {amount} ₽\n"
        f"📅 {month_name(today.month)} {today.year}"
        + (f"\n📎 Чек сохранён" if receipt_path else ""),
        parse_mode="HTML",
    )


# Import bot for file downloads — will be set in main.py
from aiogram import Bot as _Bot

# We need the bot instance for file downloads
# It will be injected via a global pattern
_bot_instance = None


def set_bot_instance(bot: _Bot):
    global _bot_instance
    _bot_instance = bot


# Override to use the bot instance
original_paid_handler = paid_handler
