"""
Dashboard route — statistics, upcoming payments, spending chart.
"""

import logging
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name, payment_color_class

logger = logging.getLogger("zhkh.dashboard")

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


async def _require_auth(request: Request):
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


def _effective_status(payment: Payment) -> str:
    """Return the effective status, treating past-due or due-today pending as overdue."""
    if payment.status == "paid":
        return "paid"
    if payment.due_date and payment.due_date <= date.today():
        return "overdue"
    return payment.status


@router.get("/")
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    today = date.today()
    year, month = today.year, today.month

    # Allow month selection via query params
    view_year = request.query_params.get("year")
    view_month = request.query_params.get("month")
    if view_year:
        year = int(view_year)
    if view_month:
        month = int(view_month)

    # Current month payments
    result = await db.execute(
        select(Payment)
        .options(joinedload(Payment.contractor))
        .where(Payment.year == year, Payment.month == month)
    )
    payments = result.scalars().all()

    total = sum((p.amount or Decimal("0")) for p in payments)
    paid = sum((p.paid_amount or Decimal("0")) for p in payments if p.status == "paid")

    pending = [p for p in payments if p.status != "paid" and _effective_status(p) != "overdue"]
    overdue = [p for p in payments if _effective_status(p) == "overdue"]

    pending_amount = sum((p.amount or Decimal("0")) for p in pending)
    overdue_amount = sum((p.amount or Decimal("0")) for p in overdue)

    # Upcoming: all unpaid payments sorted by due_date (nearest first)
    # Include pending and overdue — fetch ALL non-paid and filter/sort
    result_upcoming = await db.execute(
        select(Payment)
        .options(joinedload(Payment.contractor))
        .where(Payment.status != "paid")
        .order_by(Payment.due_date.asc())
    )
    all_unpaid = result_upcoming.scalars().all()

    # Show overdue first (sorted by due_date desc within overdue), then pending
    unpaid_overdue = sorted(
        [p for p in all_unpaid if _effective_status(p) == "overdue"],
        key=lambda p: p.due_date,
        reverse=True,
    )
    unpaid_pending = sorted(
        [p for p in all_unpaid if _effective_status(p) != "overdue"],
        key=lambda p: p.due_date,
    )
    upcoming_all = (unpaid_overdue + unpaid_pending)[:15]

    # Last 6 months data for chart
    chart_labels = []
    chart_values = []
    for i in range(5, -1, -1):
        m = month - i
        y = year
        if m <= 0:
            m += 12
            y -= 1
        result = await db.execute(
            select(func.sum(Payment.paid_amount)).where(
                Payment.year == y, Payment.month == m, Payment.status == "paid"
            )
        )
        val = result.scalar() or Decimal("0")
        chart_labels.append(month_name(m))
        chart_values.append(float(val))

    # Available months for selector
    month_options = []
    for i in range(11, -1, -1):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        month_options.append((y, m, month_name(m)))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "month_name": month_name(month),
        "year": year,
        "total": total,
        "paid": paid,
        "pending_count": len(pending),
        "pending_amount": pending_amount,
        "overdue_count": len(overdue),
        "upcoming": upcoming_all,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "month_options": month_options,
        "today": today,
        "payment_color_class": payment_color_class,
    })
