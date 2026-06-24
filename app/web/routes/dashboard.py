"""
Dashboard route — statistics, upcoming payments, spending chart.
"""

from datetime import date
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from decimal import Decimal

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name, payment_color_class

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


async def _require_auth(request: Request):
    """Redirect to login if not authenticated."""
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


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

    # Current month payments
    result = await db.execute(
        select(Payment)
        .options(joinedload(Payment.contractor))
        .where(Payment.year == year, Payment.month == month)
    )
    payments = result.scalars().all()

    total = sum((p.amount or Decimal("0")) for p in payments)
    paid = sum((p.paid_amount or Decimal("0")) for p in payments if p.status == "paid")
    pending = [p for p in payments if p.status != "paid"]
    overdue = [p for p in payments if p.status == "overdue"]

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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "month_name": month_name(month),
        "year": year,
        "total": total,
        "paid": paid,
        "pending_count": len(pending),
        "overdue_count": len(overdue),
        "upcoming": sorted(pending, key=lambda p: p.due_date)[:5],
        "chart_labels": chart_labels,
        "chart_values": chart_values,
    })
