"""
Telegram bot handlers — command and message handlers.
"""

import os
import uuid
from datetime import date
from decimal import Decimal

from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    lines = ["📋 Подрядчики:\n"]
    for c in contractors:
        if c.payment_type == "fixed" and c.fixed_amount:
            amt = f"{c.fixed_amount} ₽"
        else:
            amt = "по чеку"
        lines.append(
            f"• {c.name} (<code>#{c.slug}</code>) — {amt}, "
            f"срок: {c.due_day}-е число"
        )

    lines.append("\n💡 Для оплаты: <code>#оплачено #[slug] #сумма:X</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def paid_handler(message: Message):
    """Handle payment confirmation message: #оплачено #slug #сумма:X"""
    parsed = parse_payment_message(message.text)
    if not parsed:
        await message.answer(
            "❌ Неверный формат. Используйте: <code>#оплачено #[slug] #сумма:X</code>",
            parse_mode="HTML",
        )
        return

    today = date.today()

    async with async_session_factory() as session:
        # Find contractor by slug
        result = await session.execute(
            select(Contractor).where(Contractor.slug == parsed.slug)
        )
        contractor = result.scalar_one_or_none()

        if not contractor:
            await message.answer(
                f"❌ Подрядчик «#{parsed.slug}» не найден.\n"
                f"Попробуйте: /contractors"
            )
            return

        # Determine amount
        amount = parsed.amount
        if contractor.payment_type == "fixed" and not amount:
            amount = contractor.fixed_amount
        elif contractor.payment_type == "variable" and not amount:
            await message.answer(
                f"❌ Для «{contractor.name}» укажите сумму: <code>#сумма:[число]</code>",
                parse_mode="HTML",
            )
            return

        if amount is None:
            await message.answer("❌ Не удалось определить сумму.")
            return

        # Find pending payment for current month
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
            receipt_path = await _download_receipt(
                message, session, today.year, today.month
            )

        # Update payment
        payment.paid_amount = amount
        payment.paid_date = today
        payment.status = "paid"
        payment.receipt_file = receipt_path
        await session.commit()

    await message.answer(
        f"✅ Оплата <b>{contractor.name}</b> зафиксирована!\n"
        f"💰 Сумма: {amount} ₽\n"
        f"📅 {month_name(today.month)} {today.year}"
        + ("\n📎 Чек сохранён" if receipt_path else ""),
        parse_mode="HTML",
    )


async def _download_receipt(
    message: Message,
    session: AsyncSession,
    year: int,
    month: int,
) -> str | None:
    """Download attached photo or document as a receipt file."""
    try:
        file_obj = message.document or message.photo[-1]
        file = await message.bot.get_file(file_obj.file_id)

        ext = ".jpg"
        if message.document:
            mime = message.document.mime_type or ""
            if mime == "application/pdf":
                ext = ".pdf"
            elif mime.startswith("image/"):
                ext = "." + mime.split("/")[1]

        upload_dir = get_upload_path(year, month, UPLOAD_DIR)
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)

        await file.download_to_file(filepath)
        return f"{year}/{month:02d}/{filename}"
    except Exception as e:
        print(f"Bot receipt download error: {e}")
        return None
