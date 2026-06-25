"""
Telegram bot handlers — command and message handlers.
"""

import os
import uuid
from datetime import date

from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import Contractor, Payment
from app.bot.parsers import parse_payment_message
from app.utils import month_name, get_upload_path, is_allowed_file

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")


def _message_text(message: Message) -> str:
    """Return text or media caption for Telegram messages."""
    return message.text or message.caption or ""


async def start_handler(message: Message):
    """Handle /start command."""
    await message.answer(
        "🏠 Добро пожаловать в систему учета ЖКХ!\n\n"
        "💡 Как зафиксировать оплату:\n"
        "Перешлите чек и напишите в сообщении или подписи к чеку:\n"
        "<code>#оплачено #мосэнергосбыт #сумма:3200</code>\n\n"
        "Для старого долга добавьте период:\n"
        "<code>#оплачено #мосэнергосбыт #сумма:1000 #период:2026-06</code>\n\n"
        "Можно просто прислать чек без тегов — я спрошу подрядчика, сумму и период.\n\n"
        "📋 Команды:\n"
        "/contractors — список подрядчиков\n"
        "/cancel — отменить ввод\n"
        "/start — это сообщение",
        parse_mode="HTML",
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

    lines.append("\n💡 Для оплаты текущего месяца: <code>#оплачено #[slug] #сумма:X</code>")
    lines.append("💡 Для старого долга: <code>#оплачено #[slug] #сумма:X #период:2026-06</code>")
    lines.append("💡 Или просто пришлите чек без тегов — бот задаст вопросы.")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def paid_handler(message: Message):
    """Handle payment confirmation message: #оплачено #slug #сумма:X [#период:YYYY-MM]"""
    parsed = parse_payment_message(_message_text(message))
    if not parsed:
        await message.answer(
            "❌ Неверный формат. Используйте: "
            "<code>#оплачено #[slug] #сумма:X</code> или "
            "<code>#оплачено #[slug] #сумма:X #период:2026-06</code>",
            parse_mode="HTML",
        )
        return

    today = date.today()
    target_year = parsed.year or today.year
    target_month = parsed.month or today.month

    async with async_session_factory() as session:
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

        result = await session.execute(
            select(Payment).where(
                Payment.contractor_id == contractor.id,
                Payment.year == target_year,
                Payment.month == target_month,
            )
        )
        payment = result.scalar_one_or_none()

        if not payment:
            await message.answer(
                f"❌ Не найдена запись за {contractor.name} "
                f"за {month_name(target_month)} {target_year}.\n"
                f"Создайте платеж в веб-интерфейсе или дождитесь генерации scheduler."
            )
            return

        receipt_path = None
        if message.document or message.photo:
            receipt_path = await _download_receipt(
                message, session, target_year, target_month
            )
            if message.document and receipt_path is None:
                await message.answer("❌ Недопустимый формат файла. Пришлите PDF, JPG или PNG.")
                return

        if payment.amount is None:
            payment.amount = amount
        payment.paid_amount = amount
        payment.paid_date = today
        payment.status = "paid"
        if receipt_path:
            payment.receipt_file = receipt_path
        await session.commit()

    await message.answer(
        f"✅ Оплата <b>{contractor.name}</b> зафиксирована!\n"
        f"💰 Сумма: {amount} ₽\n"
        f"📅 Период: {month_name(target_month)} {target_year}"
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

        ext = ".jpg"
        if message.document:
            original_name = message.document.file_name or ""
            if not is_allowed_file(original_name):
                return None
            ext = os.path.splitext(original_name)[1].lower()

        file = await message.bot.get_file(file_obj.file_id)
        upload_dir = get_upload_path(year, month, UPLOAD_DIR)
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)

        await file.download_to_file(filepath)
        return f"{year}/{month:02d}/{filename}"
    except Exception as e:
        print(f"Bot receipt download error: {e}")
        return None
