"""
Shared helpers for payment status computation and display.

Used by both payments.py and history.py to avoid duplication.
"""

from datetime import date
from decimal import Decimal

from app.models import Payment


def _as_decimal(value) -> Decimal:
    """Safely convert nullable numeric DB values to Decimal."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _requires_amount(payment: Payment) -> bool:
    """Variable payment exists, but actual bill amount has not been entered yet."""
    contractor = getattr(payment, "contractor", None)
    return (
        contractor is not None
        and contractor.payment_type == "variable"
        and payment.amount is None
        and payment.paid_amount is None
        and payment.status != "paid"
    )


def _planned_amount(payment: Payment) -> Decimal:
    """Return expected charge using the same fixed-debt rule as dashboard."""
    candidates: list[Decimal] = []
    contractor = getattr(payment, "contractor", None)
    if contractor and contractor.payment_type == "fixed" and contractor.fixed_amount is not None:
        candidates.append(_as_decimal(contractor.fixed_amount))
    if payment.amount is not None:
        candidates.append(_as_decimal(payment.amount))
    if payment.paid_amount is not None:
        candidates.append(_as_decimal(payment.paid_amount))
    return max(candidates) if candidates else Decimal("0")


def _paid_amount(payment: Payment) -> Decimal:
    """Return aggregate paid amount. New transaction rows keep this field in sync."""
    return _as_decimal(payment.paid_amount)


def _remaining_amount(payment: Payment) -> Decimal:
    remaining = _planned_amount(payment) - _paid_amount(payment)
    return remaining if remaining > 0 else Decimal("0")


def _is_partial_payment(payment: Payment) -> bool:
    return _paid_amount(payment) > 0 and _remaining_amount(payment) > 0 and not _requires_amount(payment)


def _is_open_payment(payment: Payment) -> bool:
    return _remaining_amount(payment) > 0 or _requires_amount(payment)


def _effective_status(payment: Payment) -> str:
    """Return visual/business status, not just raw DB status."""
    if not _is_open_payment(payment):
        return "paid"
    if _is_partial_payment(payment):
        if payment.status == "overdue" or (payment.due_date and payment.due_date <= date.today()):
            return "partial_overdue"
        return "partial"
    if payment.status == "overdue":
        return "overdue"
    if payment.due_date and payment.due_date <= date.today():
        return "overdue"
    return "pending"


def _status_label(payment: Payment) -> str:
    status = _effective_status(payment)
    if _requires_amount(payment):
        return "ожидает начисления" if status == "pending" else "просрочено, нет суммы"
    if status == "partial_overdue":
        return "частично оплачено, просрочено"
    if status == "partial":
        return "частично оплачено"
    if status == "overdue":
        return "просрочено"
    if status == "pending":
        return "к оплате"
    return "оплачено"


def _status_css_class(payment: Payment) -> str:
    status = _effective_status(payment)
    if status == "paid":
        return "paid"
    if status == "partial":
        return "pending"
    if status == "partial_overdue":
        return "overdue"
    from app.utils import payment_color_class
    return payment_color_class(payment.due_date, status)


def _filter_by_effective_status(payments, status_filter: str):
    """Filter a list of payments by effective status."""
    if status_filter and status_filter != "all":
        return [p for p in payments if _effective_status(p) == status_filter]
    return payments
