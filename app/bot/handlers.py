"""
Telegram bot handlers — command and message handlers.
"""

import html
import logging
import os
import uuid
from datetime import date
from decimal import Decimal

from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.audit import log_admin_action
from app.bot.business_events import telegram_payment_business_details
from app.database import async_session_factory
from app.models import Contractor, Payment
from app.bot.payment_actions import (
    apply_bot_payment,
    default_bot_payment_amount,
    validate_bot_payment_amount,
)
from app.bot.parsers import parse_payment_message
from app.bot.response_templates import render_telegram_response_template
from app.bot.security import recent_telegram_messages, telegram_admin_id_for_commands
from app.config import get_settings
from app.utils import (
    MAX_FILE_SIZE,
    get_upload_path,
    is_allowed_file,
    month_name,
    validate_file_magic_bytes,
)
from app.web.routes.payment_helpers import _remaining_amount, _requires_amount, _status_label

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
logger = logging.getLogger("zhkh.bot.handlers")


def _message_text(message: Message) -> str:
    """Return text or media caption for Telegram messages."""
    return message.text or message.caption or ""


async def _response_template(name: str, context: dict[str, object] | None = None) -> str:
    """Render a Telegram response template using current DB settings."""
    async with async_session_factory() as session:
        return await render_telegram_response_template(session, name, context)


async def start_handler(message: Message):
    """Handle /start command."""
    await message.answer(await _response_template("start"), parse_mode="HTML")


async def help_handler(message: Message):
    """Handle /help command."""
    await message.answer(await _response_template("help"), parse_mode="HTML")


async def balance_handler(message: Message):
    """Handle /balance command — current month unpaid balances."""
    today = date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Payment)
            .options(joinedload(Payment.contractor))
            .where(Payment.year == today.year, Payment.month == today.month)
            .order_by(Payment.due_date.asc())
        )
        payments = result.scalars().all()

    if not payments:
        await message.answer(
            f"За {month_name(today.month)} {today.year} платежей пока нет."
        )
        return

    open_payments = [p for p in payments if _remaining_amount(p) > 0 or _requires_amount(p)]
    if not open_payments:
        await message.answer(
            f"За {month_name(today.month)} {today.year} всё оплачено."
        )
        return

    total_remaining = sum((_remaining_amount(p) for p in open_payments), start=Decimal("0"))
    lines = [
        f"Остатки за {month_name(today.month)} {today.year}:",
        f"Всего к оплате: {total_remaining} ₽",
    ]
    for payment in open_payments:
        contractor_name = payment.contractor.name if payment.contractor else "Без подрядчика"
        if _requires_amount(payment):
            amount_text = "нужно ввести сумму начисления"
        else:
            amount_text = f"остаток {_remaining_amount(payment)} ₽"
        lines.append(f"• {contractor_name}: {amount_text} ({_status_label(payment)})")

    await message.answer("\n".join(lines))


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


async def tglog_handler(message: Message):
    """Admin-only command that shows recent inbound Telegram messages."""
    settings = get_settings()
    admin_id = await telegram_admin_id_for_commands(settings.TELEGRAM_ADMIN_ID)
    sender_id = message.from_user.id if message.from_user else None

    if not admin_id or sender_id != admin_id:
        await message.answer("Команда доступна только Telegram-админу.")
        return

    limit = _parse_tglog_limit(_message_text(message))
    rows = await recent_telegram_messages(limit)
    if not rows:
        await message.answer("Журнал Telegram-сообщений пока пуст.")
        return

    lines = [f"Последние Telegram-сообщения: {len(rows)}"]
    for row in rows:
        name = row.username or "без username"
        person = " ".join(part for part in (row.first_name, row.last_name) if part).strip()
        status = "admin" if row.is_admin else ("allowed" if row.is_allowed else "blocked")
        text = (row.text or "").replace("\n", " ")
        if len(text) > 180:
            text = text[:177] + "..."
        lines.append(
            f"\n#{row.id} [{status}] user_id={row.telegram_user_id} @{html.escape(name)}"
            + (f" ({html.escape(person)})" if person else "")
            + f"\nchat={row.chat_id} type={html.escape(str(row.message_type))}"
            + f"\n{html.escape(text) if text else '<i>без текста</i>'}"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


async def paid_handler(message: Message):
    """Handle payment confirmation message: #оплачено #slug #сумма:X [#период:YYYY-MM]"""
    parsed = parse_payment_message(_message_text(message))
    if not parsed:
        await message.answer(
            await _response_template("error_invalid_payment_format"),
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

        result = await session.execute(
            select(Payment)
            .options(joinedload(Payment.contractor))
            .where(
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

        amount = parsed.amount
        if amount is None:
            amount = default_bot_payment_amount(payment)
            if amount is None:
                await message.answer(
                    f"❌ Для «{contractor.name}» укажите сумму: <code>#сумма:[число]</code>",
                    parse_mode="HTML",
                )
                return

        valid, error_message = validate_bot_payment_amount(payment, amount)
        if not valid:
            await message.answer(f"❌ {error_message}")
            return

        receipt_path = None
        if message.document or message.photo:
            receipt_path = await _download_receipt(
                message, session, target_year, target_month
            )
            if receipt_path is None:
                await message.answer(
                    await render_telegram_response_template(
                        session,
                        "error_invalid_receipt_file",
                    ),
                    parse_mode="HTML",
                )
                return

        ok, apply_message = apply_bot_payment(
            session,
            payment=payment,
            amount=amount,
            paid_date=today,
            receipt_path=receipt_path,
        )
        if not ok:
            await message.answer(f"❌ {apply_message}")
            return
        await log_admin_action(
            session,
            actor=None,
            action="telegram_payment_recorded",
            entity_type="payment",
            entity_id=payment.id,
            details=telegram_payment_business_details(
                message=message,
                payment_id=str(payment.id),
                contractor_id=str(contractor.id),
                contractor_name=str(contractor.name),
                amount=amount,
                year=target_year,
                month=target_month,
                receipt_path=receipt_path,
            ),
        )
        await session.commit()
        payment_confirmation_text = await render_telegram_response_template(
            session,
            "payment_confirmation",
            {
                "contractor_name": html.escape(str(contractor.name)),
                "amount": amount,
                "period": f"{month_name(target_month)} {target_year}",
                "receipt_saved_line": "\n📎 Чек сохранён" if receipt_path else "",
            },
        )

    await message.answer(payment_confirmation_text, parse_mode="HTML")


def _telegram_admin_id(raw: str) -> int | None:
    try:
        return int(raw.strip()) if raw and raw.strip() else None
    except ValueError:
        return None


def _parse_tglog_limit(text: str) -> int:
    parts = text.split()
    if len(parts) < 2:
        return 20
    try:
        return min(max(int(parts[1]), 1), 50)
    except ValueError:
        return 20


async def _download_receipt(
    message: Message,
    session: AsyncSession,
    year: int,
    month: int,
) -> str | None:
    """Download, validate and save attached photo or document as a receipt file."""
    tmp_filepath = None
    try:
        file_obj = message.document or message.photo[-1]

        ext = ".jpg"
        if message.document:
            original_name = message.document.file_name or ""
            if not is_allowed_file(original_name):
                return None
            ext = os.path.splitext(original_name)[1].lower()

        declared_size = getattr(file_obj, "file_size", None)
        if declared_size is not None and declared_size > MAX_FILE_SIZE:
            return None

        file = await message.bot.get_file(file_obj.file_id)
        upload_dir = get_upload_path(year, month, UPLOAD_DIR)
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)
        tmp_filepath = f"{filepath}.tmp"

        await file.download_to_file(tmp_filepath)
        with open(tmp_filepath, "rb") as uploaded:
            content = uploaded.read(MAX_FILE_SIZE + 1)

        if len(content) > MAX_FILE_SIZE:
            return None
        if not validate_file_magic_bytes(content, ext):
            return None

        os.replace(tmp_filepath, filepath)
        tmp_filepath = None
        return f"{year}/{month:02d}/{filename}"
    except Exception as e:
        logger.warning("Bot receipt download error: %s", e)
        return None
    finally:
        if tmp_filepath and os.path.exists(tmp_filepath):
            try:
                os.remove(tmp_filepath)
            except OSError:
                logger.warning("Could not remove temporary bot receipt file: %s", tmp_filepath)
