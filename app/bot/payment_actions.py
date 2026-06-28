"""Shared Telegram bot payment operations."""

from datetime import date
from decimal import Decimal
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentTransaction
from app.web.routes.payment_helpers import (
    _as_decimal,
    _planned_amount,
    _paid_amount,
    _remaining_amount,
    _requires_amount,
)


def _is_variable_payment(payment: Payment) -> bool:
    contractor = getattr(payment, "contractor", None)
    return contractor is not None and contractor.payment_type == "variable"


def _sync_payment_status_from_amounts(payment: Payment) -> None:
    if _remaining_amount(payment) <= 0 and not _requires_amount(payment):
        payment.status = "paid"
    elif payment.status == "paid":
        payment.status = "pending"


def default_bot_payment_amount(payment: Payment) -> Decimal | None:
    """Return suggested amount for Telegram flows."""
    if _is_variable_payment(payment):
        return None
    remaining = _remaining_amount(payment)
    return remaining if remaining > 0 else None


def validate_bot_payment_amount(payment: Payment, amount: Decimal) -> tuple[bool, str]:
    """Validate Telegram payment amount before receipt download or DB mutation."""
    if amount <= 0:
        return False, "Сумма оплаты должна быть больше нуля."

    if _is_variable_payment(payment):
        return True, "ok"

    planned = _planned_amount(payment)
    remaining = _remaining_amount(payment)
    if planned <= 0:
        return False, "Сначала укажите сумму начисления в веб-интерфейсе."
    if remaining <= 0:
        return False, "Этот платеж уже полностью оплачен."
    if amount > remaining:
        return False, f"Сумма больше остатка. Остаток к оплате: {remaining} ₽."
    return True, "ok"


def apply_bot_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    amount: Decimal,
    paid_date: date,
    receipt_path: str | None,
) -> tuple[bool, str]:
    """Apply a Telegram payment as a transaction and refresh legacy aggregates."""
    valid, message = validate_bot_payment_amount(payment, amount)
    if not valid:
        return False, message
    is_variable = _is_variable_payment(payment)
    planned = _planned_amount(payment)

    new_paid_total = _paid_amount(payment) + amount
    if is_variable and (payment.amount is None or _as_decimal(payment.amount) < new_paid_total):
        payment.amount = new_paid_total
    elif payment.amount is None:
        payment.amount = planned

    tx = PaymentTransaction(
        id=f"tx-bot-{uuid.uuid4().hex}",
        payment_id=payment.id,
        amount=amount,
        paid_date=paid_date,
        receipt_file=receipt_path,
        notes="Created from Telegram bot",
    )
    session.add(tx)

    payment.paid_amount = new_paid_total
    payment.paid_date = paid_date
    if receipt_path and not payment.receipt_file:
        payment.receipt_file = receipt_path
    _sync_payment_status_from_amounts(payment)
    return True, "ok"
