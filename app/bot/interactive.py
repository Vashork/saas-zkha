"""Interactive Telegram receipt workflow."""

import logging
import os
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import async_session_factory
from app.models import Contractor, Payment
from app.bot.payment_actions import apply_bot_payment, default_bot_payment_amount, validate_bot_payment_amount
from app.utils import get_upload_path, is_allowed_file, month_name
from app.web.routes.payment_helpers import _remaining_amount

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
logger = logging.getLogger("zhkh.bot.interactive")

MONTH_ALIASES = {
    "январь": 1,
    "января": 1,
    "февраль": 2,
    "февраля": 2,
    "март": 3,
    "марта": 3,
    "апрель": 4,
    "апреля": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июль": 7,
    "июля": 7,
    "август": 8,
    "августа": 8,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "ноябрь": 11,
    "ноября": 11,
    "декабрь": 12,
    "декабря": 12,
}


class ReceiptFlow(StatesGroup):
    contractor = State()
    amount = State()
    period = State()
    confirm = State()


async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Ок, ввод отменён. Чек не сохранён.")


async def receipt_start_handler(message: Message, state: FSMContext):
    info = _receipt_info(message)
    if not info:
        await message.answer("Недопустимый формат файла. Пришлите PDF, JPG или PNG.")
        return

    async with async_session_factory() as session:
        contractors = (await session.execute(
            select(Contractor).where(Contractor.is_active == True).order_by(Contractor.name)
        )).scalars().all()

    if not contractors:
        await message.answer("Подрядчиков пока нет. Добавьте их через веб-интерфейс.")
        return

    await state.clear()
    await state.set_state(ReceiptFlow.contractor)
    await state.update_data(**info)

    lines = ["Чек получил. Укажите подрядчика: номер или slug."]
    for idx, c in enumerate(contractors, 1):
        lines.append(f"{idx}. {c.name} — #{c.slug}")
    await message.answer("\n".join(lines))


async def receipt_contractor_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower().lstrip("#")
    if _is_cancel(raw):
        await _cancel_flow(message, state)
        return

    async with async_session_factory() as session:
        contractors = (await session.execute(
            select(Contractor).where(Contractor.is_active == True).order_by(Contractor.name)
        )).scalars().all()

        contractor = None
        if raw.isdigit() and 1 <= int(raw) <= len(contractors):
            contractor = contractors[int(raw) - 1]
        if contractor is None:
            contractor = (await session.execute(select(Contractor).where(Contractor.slug == raw))).scalar_one_or_none()
        if contractor is None:
            contractor = next((c for c in contractors if c.name.lower() == raw), None)

    if contractor is None:
        await message.answer("Подрядчик не найден. Напишите номер или slug ещё раз.")
        return

    await state.update_data(
        contractor_id=contractor.id,
        contractor_name=contractor.name,
        payment_type=contractor.payment_type,
        fixed_amount=str(contractor.fixed_amount or ""),
    )
    await state.set_state(ReceiptFlow.period)

    await message.answer(
        f"Подрядчик: {contractor.name}\n\n"
        "Введите месяц оплаты.\n\n"
        "Для отмены отправьте /cancel."
    )


async def receipt_amount_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    raw = (message.text or "").strip().lower()
    if _is_cancel(raw):
        await _cancel_flow(message, state)
        return

    amount = None
    if raw == "" and data.get("default_amount"):
        amount = Decimal(data["default_amount"])
    else:
        amount = _to_decimal(raw)

    if amount is None or amount <= 0:
        default_text = f" Можно ввести сумму долга: {data['default_amount']} ₽." if data.get("default_amount") else ""
        await message.answer(f"Не понял сумму. Введите число, например 3200.{default_text} Для отмены отправьте /cancel.")
        return

    async with async_session_factory() as session:
        payment = (await session.execute(
            select(Payment)
            .options(joinedload(Payment.contractor))
            .where(Payment.id == data["payment_id"])
        )).scalar_one_or_none()
        if not payment:
            await state.clear()
            await message.answer("Платёж уже не найден. Проверьте веб-интерфейс.")
            return
        valid, error_message = validate_bot_payment_amount(payment, amount)

    if not valid:
        await message.answer(f"{error_message} Введите другую сумму или отправьте /cancel для отмены.")
        return

    await state.update_data(amount=str(amount))
    await state.set_state(ReceiptFlow.confirm)
    await message.answer(
        f"Проверьте данные:\n"
        f"Подрядчик: {data['contractor_name']}\n"
        f"Сумма: {amount} ₽\n"
        f"Период: {month_name(int(data['month']))} {data['year']}\n"
        "Если всё верно, напишите «да». Если нет — напишите «нет». Для отмены отправьте /cancel."
    )


async def receipt_period_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    raw = (message.text or "").strip().lower()
    today = date.today()

    if _is_cancel(raw):
        await _cancel_flow(message, state)
        return

    year, month = _parse_period(raw, today=today)

    if not year or not month:
        await message.answer("Не понял период. Введите, например: июнь, июнь 2026, 2026-июнь, 06.26 или 2026-06.")
        return

    async with async_session_factory() as session:
        payment = (await session.execute(
            select(Payment)
            .options(joinedload(Payment.contractor))
            .where(
                Payment.contractor_id == data["contractor_id"],
                Payment.year == year,
                Payment.month == month,
            )
        )).scalar_one_or_none()

    if not payment:
        await state.clear()
        await message.answer(
            f"Не найдена запись за {data['contractor_name']} за {month_name(month)} {year}. "
            f"Создайте платёж в веб-интерфейсе и повторите загрузку."
        )
        return

    default_amount = default_bot_payment_amount(payment)
    await state.update_data(
        year=year,
        month=month,
        payment_id=payment.id,
        default_amount=str(default_amount) if default_amount is not None else "",
    )
    await state.set_state(ReceiptFlow.amount)

    if default_amount is not None:
        await message.answer(
            f"Остаток по {data['contractor_name']} за {month_name(month)} {year}: {_remaining_amount(payment)} ₽.\n"
            f"Введите сумму долга {default_amount} ₽ или иную сумму.\n"
            "Для отмены отправьте /cancel."
        )
    else:
        await message.answer(
            f"Введите сумму оплаты за {month_name(month)} {year}, например 3200.\n"
            "Для отмены отправьте /cancel."
        )


async def receipt_confirm_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    if raw in {"да", "yes", "y", "ок", "сохранить"}:
        should_save = True
    elif raw in {"нет", "no", "n"}:
        should_save = False
    elif _is_cancel(raw):
        await _cancel_flow(message, state)
        return
    else:
        await message.answer("Введите «да» для сохранения или «нет» для отмены. Для отмены можно отправить /cancel.")
        return

    if not should_save:
        await state.clear()
        await message.answer("Ок, оплату не сохраняю.")
        return

    data = await state.get_data()
    amount = Decimal(data["amount"])
    year = int(data["year"])
    month = int(data["month"])
    today = date.today()

    async with async_session_factory() as session:
        payment = (await session.execute(
            select(Payment)
            .options(joinedload(Payment.contractor))
            .where(Payment.id == data["payment_id"])
        )).scalar_one_or_none()
        if not payment:
            await state.clear()
            await message.answer("Платёж уже не найден. Проверьте веб-интерфейс.")
            return

        receipt_path = await _download_by_file_id(message, data["file_id"], data["file_ext"], year, month)
        if not receipt_path:
            await state.clear()
            await message.answer("Не удалось сохранить чек. Попробуйте ещё раз.")
            return

        ok, apply_message = apply_bot_payment(
            session,
            payment=payment,
            amount=amount,
            paid_date=today,
            receipt_path=receipt_path,
        )
        if not ok:
            await state.clear()
            await message.answer(apply_message)
            return
        await session.commit()

    await state.clear()
    await message.answer(
        f"Оплата сохранена.\nСумма: {amount} ₽\nПериод: {month_name(month)} {year}\nЧек сохранён."
    )


def _receipt_info(message: Message) -> dict | None:
    if message.photo:
        return {"file_id": message.photo[-1].file_id, "file_ext": ".jpg"}
    if message.document:
        name = message.document.file_name or ""
        if not is_allowed_file(name):
            return None
        return {"file_id": message.document.file_id, "file_ext": os.path.splitext(name)[1].lower()}
    return None


def _to_decimal(raw: str) -> Decimal | None:
    try:
        raw = raw.replace(" ", "").replace("_", "")
        if "," in raw and "." in raw:
            raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", ".")
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _is_cancel(raw: str) -> bool:
    return raw in {"/cancel", "/cancle"}


async def _cancel_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, ввод отменён. Чек не сохранён.")


def _parse_period(raw: str, today: date | None = None) -> tuple[int | None, int | None]:
    today = today or date.today()
    normalized = raw.strip().lower().replace("ё", "е")
    if not normalized:
        return None, None

    if normalized in MONTH_ALIASES:
        return today.year, MONTH_ALIASES[normalized]

    parts = [part for part in normalized.replace("-", " ").replace("/", " ").replace(".", " ").split() if part]
    if len(parts) == 2:
        first, second = parts
        year = _parse_year(first) or _parse_year(second)
        month = _parse_month(first) or _parse_month(second)
        if year and month:
            return year, month

    for sep in ("-", ".", "/"):
        if sep in normalized:
            parts = normalized.split(sep)
            if len(parts) != 2:
                return None, None
            try:
                year, month = int(parts[0]), int(parts[1])
            except ValueError:
                return None, None
            if 2000 <= year <= 2100 and 1 <= month <= 12:
                return year, month
    return None, None


def _parse_month(value: str) -> int | None:
    if value in MONTH_ALIASES:
        return MONTH_ALIASES[value]
    try:
        month = int(value)
    except ValueError:
        return None
    return month if 1 <= month <= 12 else None


def _parse_year(value: str) -> int | None:
    try:
        year = int(value)
    except ValueError:
        return None
    if 0 <= year <= 99:
        year += 2000
    return year if 2000 <= year <= 2100 else None


async def _download_by_file_id(message: Message, file_id: str, ext: str, year: int, month: int) -> str | None:
    try:
        tg_file = await message.bot.get_file(file_id)
        upload_dir = get_upload_path(year, month, UPLOAD_DIR)
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)
        await message.bot.download_file(tg_file.file_path, destination=filepath)
        return f"{year}/{month:02d}/{filename}"
    except Exception as exc:
        logger.warning("Interactive receipt download error: %s", exc)
        return None
