"""
Analytics route — charts and spending analysis.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name
from app.web.routes.auth import _require_page

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def _month_conditions(year_val, month_val=None):
    """Return a list of WHERE conditions for year (+ optional month)."""
    conditions = [Payment.year == year_val, Payment.status == "paid"]
    if month_val:
        conditions.append(Payment.month == month_val)
    return conditions


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

    target_year = year or date.today().year
    target_month = month  # None = all year
    prev_year = target_year - 1

    if target_month:
        # --- Single-month mode: compare this month year-over-year ---
        monthly_labels = [month_name(target_month)]
        vals_prev = []
        vals_curr = []
        for yv in [prev_year, target_year]:
            result = await db.execute(
                select(func.sum(Payment.paid_amount)).where(
                    *_month_conditions(yv, target_month)
                )
            )
            vals_prev.append(float(result.scalar() or Decimal("0")))

        monthly_previous = vals_prev  # [prev_year_val]
        monthly_current = [float(
            (await db.execute(
                select(func.sum(Payment.paid_amount)).where(
                    *_month_conditions(target_year, target_month)
                )
            )).scalar() or Decimal("0")
        )]

        # Contractor totals for this month
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

        # Trends for selected month across past 5 years
        trends = []
        contractors_result = await db.execute(
            select(Contractor).where(Contractor.is_active == True)
        )
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
                        Payment.status == "paid",
                    )
                )
                years_vals.append(float(result.scalar() or Decimal("0")))
                yr_labels.append(str(yr))
            trends.append({"name": c.name, "values": years_vals, "labels": yr_labels})

        # YoY for this month
        current_total = monthly_current[0]
        prev_total = monthly_previous[0]

    else:
        # --- Full-year mode: 12 months, current vs previous year ---
        monthly_labels = []
        monthly_current = []
        monthly_previous = []
        for m in range(1, 13):
            monthly_labels.append(month_name(m))
            for yv, vals in [(prev_year, monthly_previous), (target_year, monthly_current)]:
                result = await db.execute(
                    select(func.sum(Payment.paid_amount)).where(
                        *_month_conditions(yv, m)
                    )
                )
                vals.append(float(result.scalar() or Decimal("0")))

        # Contractor totals for the year
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

        # Per-contractor monthly trend
        trends = []
        contractors_result = await db.execute(
            select(Contractor).where(Contractor.is_active == True)
        )
        for c in contractors_result.scalars().all():
            months_vals = []
            for m in range(1, 13):
                result = await db.execute(
                    select(func.sum(Payment.paid_amount)).where(
                        Payment.contractor_id == c.id,
                        Payment.year == target_year,
                        Payment.month == m,
                        Payment.status == "paid",
                    )
                )
                months_vals.append(float(result.scalar() or Decimal("0")))
            trends.append({"name": c.name, "values": months_vals})

        # YoY for the year
        current_total = float(
            (await db.execute(
                select(func.sum(Payment.paid_amount)).where(
                    *_month_conditions(target_year)
                )
            )).scalar() or Decimal("0")
        )
        prev_total = float(
            (await db.execute(
                select(func.sum(Payment.paid_amount)).where(
                    *_month_conditions(prev_year)
                )
            )).scalar() or Decimal("0")
        )

    yoy_pct = ((current_total - prev_total) / prev_total * 100) if prev_total > 0 else 0

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "year": target_year,
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
