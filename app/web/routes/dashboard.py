"""
Dashboard route — statistics, upcoming payments, spending chart.
"""

import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Payment
from app.utils import month_name, payment_color_class
from app.web.routes.auth import _require_page, get_current_user

logger = logging.getLogger("zhkh.dashboard")

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def _as_decimal(value) -> Decimal:
    """Safely convert nullable numeric DB values to Decimal."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _requires_amount(payment: Payment) -> bool:
    """Variable payment exists, but the actual bill amount has not been entered yet."""
    contractor = getattr(payment, "contractor", None)
    return (
        contractor is not None
        and contractor.payment_type == "variable"
        and payment.amount is None
        and payment.paid_amount is None
        and payment.status != "paid"
    )


def _planned_amount(payment: Payment) -> Decimal:
    """
    Return the amount that should be treated as the expected charge.

    For variable contractors without an entered bill amount this intentionally
    returns 0; such payments are still tracked by _requires_amount().
    """
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
    """Return paid amount for calculations."""
    return _as_decimal(payment.paid_amount)


def _remaining_amount(payment: Payment) -> Decimal:
    """Return unpaid remainder, never below zero."""
    remaining = _planned_amount(payment) - _paid_amount(payment)
    return remaining if remaining > 0 else Decimal("0")


def _is_open_payment(payment: Payment) -> bool:
    """Open means real debt exists or a variable bill amount still needs to be entered."""
    return _remaining_amount(payment) > 0 or _requires_amount(payment)


def _effective_status(payment: Payment) -> str:
    """Return effective status based on remaining debt, missing variable amount and due date."""
    if not _is_open_payment(payment):
        return "paid"
    if payment.status == "overdue":
        return "overdue"
    if payment.due_date and payment.due_date <= date.today():
        return "overdue"
    return "pending"


def _status_label(payment: Payment) -> str:
    """Human-readable status label for the dashboard table."""
    status = _effective_status(payment)
    if _requires_amount(payment):
        return "ожидает начисления" if status == "pending" else "просрочено, нет суммы"
    if status == "overdue":
        return "просрочено"
    if status == "pending":
        return "к оплате"
    return "оплачено"


def _status_css_class(payment: Payment) -> str:
    """CSS class for dashboard status badges."""
    status = _effective_status(payment)
    if status == "paid":
        return "paid"
    return payment_color_class(payment.due_date, status)


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    """Shift a year/month pair by N months and return normalized (year, month)."""
    month_index = year * 12 + (month - 1) + offset
    return month_index // 12, month_index % 12 + 1


def _parse_selected_period(request: Request, today: date) -> tuple[int, int]:
    """Parse selected year/month from query params with safe fallback to today."""
    year = today.year
    month = today.month

    try:
        year = int(request.query_params.get("year", year))
    except (TypeError, ValueError):
        year = today.year

    try:
        month = int(request.query_params.get("month", month))
    except (TypeError, ValueError):
        month = today.month

    if not 1 <= month <= 12:
        month = today.month
    if year < 2000 or year > 2100:
        year = today.year

    return year, month


async def _build_month_options(db: AsyncSession, selected_year: int, selected_month: int, today: date):
    """Build robust selector options."""
    month_keys = {(selected_year, selected_month)}

    for offset in range(-23, 13):
        month_keys.add(_shift_month(today.year, today.month, offset))

    result = await db.execute(
        select(Payment.year, Payment.month)
        .distinct()
        .order_by(Payment.year.desc(), Payment.month.desc())
    )
    for y, m in result.all():
        if y and m and 1 <= m <= 12:
            month_keys.add((int(y), int(m)))

    return [(y, m, month_name(m)) for y, m in sorted(month_keys, reverse=True)]


def _subtext_with_missing(total_count: int, missing_count: int, label: str) -> str:
    if missing_count:
        return f"{total_count} {label}, включая {missing_count} без суммы"
    return f"{total_count} {label}"


@router.get("/")
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect = await _require_page(request, "dashboard")
    if redirect:
        return redirect

    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    today = date.today()
    year, month = _parse_selected_period(request, today)

    result = await db.execute(
        select(Payment)
        .options(joinedload(Payment.contractor))
        .where(Payment.year == year, Payment.month == month)
    )
    payments = result.scalars().all()

    total = sum((_planned_amount(p) for p in payments), Decimal("0"))
    paid = sum((_paid_amount(p) for p in payments), Decimal("0"))

    pending = []
    overdue = []
    for p in payments:
        eff = _effective_status(p)
        if eff == "paid":
            continue
        if eff == "overdue":
            overdue.append(p)
        else:
            pending.append(p)

    pending_amount = sum((_remaining_amount(p) for p in pending), Decimal("0"))
    overdue_amount = sum((_remaining_amount(p) for p in overdue), Decimal("0"))
    unpaid_amount = pending_amount + overdue_amount
    unpaid_count = len(pending) + len(overdue)
    unpaid_missing_amount_count = sum(1 for p in pending + overdue if _requires_amount(p))
    overdue_missing_amount_count = sum(1 for p in overdue if _requires_amount(p))
    unpaid_subtext = _subtext_with_missing(unpaid_count, unpaid_missing_amount_count, "открытых платеж(ей)")
    overdue_subtext = _subtext_with_missing(overdue_count := len(overdue), overdue_missing_amount_count, "просроченных платеж(ей)")

    result_upcoming = await db.execute(
        select(Payment)
        .options(joinedload(Payment.contractor))
        .order_by(Payment.due_date.asc())
    )
    all_payments = result_upcoming.scalars().all()
    all_unpaid = [p for p in all_payments if _is_open_payment(p)]

    unpaid_overdue = sorted(
        [p for p in all_unpaid if _effective_status(p) == "overdue"],
        key=lambda p: p.due_date or date.max,
        reverse=True,
    )
    unpaid_pending = sorted(
        [p for p in all_unpaid if _effective_status(p) != "overdue"],
        key=lambda p: p.due_date or date.max,
    )
    upcoming_all = (unpaid_overdue + unpaid_pending)[:15]

    chart_labels = []
    chart_values = []
    for offset in range(-5, 1):
        y, m = _shift_month(year, month, offset)
        result = await db.execute(
            select(func.sum(Payment.paid_amount)).where(
                Payment.year == y, Payment.month == m, Payment.paid_amount.is_not(None)
            )
        )
        val = result.scalar() or Decimal("0")
        chart_labels.append(f"{month_name(m)} {y}")
        chart_values.append(float(val))

    month_options = await _build_month_options(db, year, month, today)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "month_name": month_name(month),
        "year": year,
        "month": month,
        "total": total,
        "paid": paid,
        "pending_count": len(pending),
        "pending_amount": pending_amount,
        "overdue_count": overdue_count,
        "overdue_amount": overdue_amount,
        "unpaid_count": unpaid_count,
        "unpaid_amount": unpaid_amount,
        "unpaid_subtext": unpaid_subtext,
        "overdue_subtext": overdue_subtext,
        "upcoming": upcoming_all,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "month_options": month_options,
        "today": today,
        "payment_color_class": payment_color_class,
        "planned_amount": _planned_amount,
        "paid_amount": _paid_amount,
        "remaining_amount": _remaining_amount,
        "requires_amount": _requires_amount,
        "effective_status": _effective_status,
        "status_label": _status_label,
        "status_css_class": _status_css_class,
    })
