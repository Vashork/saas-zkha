"""
Analytics route — charts and spending analysis.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name
from app.web.routes.auth import _require_page, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def _month_conditions(year_val, month_val=None):
    """Return a list of WHERE conditions for year (+ optional month)."""
    conditions = [Payment.year == year_val, Payment.paid_amount.is_not(None)]
    if month_val:
        conditions.append(Payment.month == month_val)
    return conditions


async def _sum_paid(db: AsyncSession, year_val: int, month_val: int | None = None) -> float:
    """Return paid sum for a year or a concrete month."""
    result = await db.execute(
        select(func.sum(Payment.paid_amount)).where(*_month_conditions(year_val, month_val))
    )
    return float(result.scalar() or Decimal("0"))


async def _build_year_options(db: AsyncSession, selected_year: int) -> list[int]:
    """Build stable year selector options from DB + current/selected years."""
    current_year = date.today().year
    years = {selected_year, current_year, current_year - 1, current_year - 2, current_year - 3, current_year - 4}

    result = await db.execute(select(Payment.year).distinct().order_by(Payment.year.desc()))
    for row in result.all():
        if row[0]:
            years.add(int(row[0]))

    return sorted(years, reverse=True)


@router.get("/analytics")
async def analytics_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: int = None,
    month: int = None,
):
    redirect = await _require_page(request, "analytics")
    if redirect:
        return redirect

    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    today = date.today()
    target_year = year or today.year
    if target_year < 2000 or target_year > 2100:
        target_year = today.year

    target_month = month if month and 1 <= month <= 12 else None
    prev_year = target_year - 1
    year_options = await _build_year_options(db, target_year)

    if target_month:
        # Single-month mode: compare one selected month year-over-year.
        monthly_labels = [month_name(target_month)]
        previous_value = await _sum_paid(db, prev_year, target_month)
        current_value = await _sum_paid(db, target_year, target_month)
        monthly_previous = [previous_value]
        monthly_current = [current_value]

        result = await db.execute(
            select(Contractor.name, func.sum(Payment.paid_amount))
            .join(Payment, Payment.contractor_id == Contractor.id)
            .where(*_month_conditions(target_year, target_month))
            .group_by(Contractor.id)
            .order_by(func.sum(Payment.paid_amount).desc())
        )
        top5_contractors = [
            {"name": row[0], "total": float(row[1] or Decimal("0"))}
            for row in result.all()[:5]
        ]

        trends = []
        contractors_result = await db.execute(select(Contractor).where(Contractor.is_active == True))
        for c in contractors_result.scalars().all():
            years_vals = []
            yr_labels = []
            for yr_off in range(4, -1, -1):
                yr = target_year - yr_off
                result = await db.execute(
                    select(func.sum(Payment.paid_amount)).where(
                        Payment.contractor_id == c.id,
                        Payment.year == yr,
                        Payment.month == target_month,
                        Payment.paid_amount.is_not(None),
                    )
                )
                years_vals.append(float(result.scalar() or Decimal("0")))
                yr_labels.append(str(yr))
            trends.append({"name": c.name, "values": years_vals, "labels": yr_labels})

        current_total = current_value
        prev_total = previous_value

    else:
        # Full-year mode: 12 months, current vs previous year.
        monthly_labels = []
        monthly_current = []
        monthly_previous = []
        for m in range(1, 13):
            monthly_labels.append(month_name(m))
            monthly_previous.append(await _sum_paid(db, prev_year, m))
            monthly_current.append(await _sum_paid(db, target_year, m))

        result = await db.execute(
            select(Contractor.name, func.sum(Payment.paid_amount))
            .join(Payment, Payment.contractor_id == Contractor.id)
            .where(*_month_conditions(target_year))
            .group_by(Contractor.id)
            .order_by(func.sum(Payment.paid_amount).desc())
        )
        top5_contractors = [
            {"name": row[0], "total": float(row[1] or Decimal("0"))}
            for row in result.all()[:5]
        ]

        trends = []
        contractors_result = await db.execute(select(Contractor).where(Contractor.is_active == True))
        for c in contractors_result.scalars().all():
            months_vals = []
            for m in range(1, 13):
                result = await db.execute(
                    select(func.sum(Payment.paid_amount)).where(
                        Payment.contractor_id == c.id,
                        Payment.year == target_year,
                        Payment.month == m,
                        Payment.paid_amount.is_not(None),
                    )
                )
                months_vals.append(float(result.scalar() or Decimal("0")))
            trends.append({"name": c.name, "values": months_vals})

        current_total = await _sum_paid(db, target_year)
        prev_total = await _sum_paid(db, prev_year)

    yoy_pct = ((current_total - prev_total) / prev_total * 100) if prev_total > 0 else 0

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "year": target_year,
        "year_options": year_options,
        "prev_year": prev_year,
        "month": target_month,
        "monthly_labels": monthly_labels,
        "monthly_current": monthly_current,
        "monthly_previous": monthly_previous,
        "top5_contractors": top5_contractors,
        "trends": trends,
        "current_total": current_total,
        "prev_total": prev_total,
        "yoy_pct": round(yoy_pct, 1),
        "month_name": month_name,
    })
