"""Interactive Telegram receipt workflow."""

import os
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select

from app.database import async_session_factory
from app.models import Contractor, Payment
from app.utils import get_upload_path, is_allowed_file, month_name

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")


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
    lines.append("Для отмены: /cancel")
    await message.answer("\n".join(lines))


async def receipt_contractor_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower().lstrip("#")
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
        await message.answer("Подрядчик не найден. Напишите номер/slug ещё раз или /cancel.")
        return

    await state.update_data(
        contractor_id=contractor.id,
        contractor_name=contractor.name,
        payment_type=contractor.payment_type,
        fixed_amount=str(contractor.fixed_amount or ""),
    )
    await state.set_state(ReceiptFlow.amount)

    if contractor.payment_type == "fixed" and contractor.fixed_amount is not None:
        await message.answer(
            f"Подрядчик: {contractor.name}\n"
            f"Плановая сумма: {contractor.fixed_amount} ₽.\n"
            f"Напишите сумму или 'по умолчанию'."
        )
    else:
        await message.answer(f"Подрядчик: {contractor.name}\nНапишите сумму, например 3200.")


async def receipt_amount_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    raw = (message.text or "").strip().lower()

    amount = None
    if raw in {"по умолчанию", "default", "фикс"} and data.get("fixed_amount"):
        amount = Decimal(data["fixed_amount"])
    else:
        amount = _to_decimal(raw)

    if amount is None or amount <= 0:
        await message.answer("Не понял сумму. Напишите число, например 3200, или /cancel.")
        return

    await state.update_data(amount=str(amount))
    await state.set_state(ReceiptFlow.period)
    await message.answer("Укажите период: 2026-06 или 'текущий'.")


async def receipt_period_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    raw = (message.text or "").strip().lower()
    today = date.today()

    if raw in {"текущий", "current", "сейчас"}:
        year, month = today.year, today.month
    else:
        year, month = _parse_period(raw)

    if not year or not month:
        await message.answer("Не понял период. Напишите 2026-06 или 'текущий'.")
        return

    async with async_session_factory() as session:
        payment = (await session.execute(select(Payment).where(
            Payment.contractor_id == data["contractor_id"],
            Payment.year == year,
            Payment.month == month,
        ))).scalar_one_or_none()

    if not payment:
        await state.clear()
        await message.answer(
            f"Не найдена запись за {data['contractor_name']} за {month_name(month)} {year}. "
            f"Создайте платёж в веб-интерфейсе и повторите загрузку."
        )
        return

    await state.update_data(year=year, month=month, payment_id=payment.id)
    await state.set_state(ReceiptFlow.confirm)
    await message.answer(
        f"Проверьте данные:\n"
        f"Подрядчик: {data['contractor_name']}\n"
        f"Сумма: {data['amount']} ₽\n"
        f"Период: {month_name(month)} {year}\n"
        f"Сохранить? Напишите да или нет."
    )


async def receipt_confirm_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    if raw not in {"да", "yes", "y", "ок", "сохранить"}:
        await state.clear()
        await message.answer("Ок, оплату не сохраняю.")
        return

    data = await state.get_data()
    amount = Decimal(data["amount"])
    year = int(data["year"])
    month = int(data["month"])
    today = date.today()

    async with async_session_factory() as session:
        payment = (await session.execute(select(Payment).where(Payment.id == data["payment_id"]))).scalar_one_or_none()
        if not payment:
            await state.clear()
            await message.answer("Платёж уже не найден. Проверьте веб-интерфейс.")
            return

        receipt_path = await _download_by_file_id(message, data["file_id"], data["file_ext"], year, month)
        if not receipt_path:
            await state.clear()
            await message.answer("Не удалось сохранить чек. Попробуйте ещё раз.")
            return

        if payment.amount is None:
            payment.amount = amount
        payment.paid_amount = amount
        payment.paid_date = today
        payment.status = "paid"
        payment.receipt_file = receipt_path
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


def _parse_period(raw: str) -> tuple[int | None, int | None]:
    for sep in ("-", ".", "/"):
        if sep in raw:
            parts = raw.split(sep)
            if len(parts) != 2:
                return None, None
            try:
                year, month = int(parts[0]), int(parts[1])
            except ValueError:
                return None, None
            if 2000 <= year <= 2100 and 1 <= month <= 12:
                return year, month
    return None, None


async def _download_by_file_id(message: Message, file_id: str, ext: str, year: int, month: int) -> str | None:
    try:
        tg_file = await message.bot.get_file(file_id)
        upload_dir = get_upload_path(year, month, UPLOAD_DIR)
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)
        await message.bot.download_file(tg_file.file_path, destination=filepath)
        return f"{year}/{month:02d}/{filename}"
    except Exception as exc:
        print(f"Interactive receipt download error: {exc}")
        return None
