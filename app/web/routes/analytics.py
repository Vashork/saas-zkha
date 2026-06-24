"""
Analytics route — charts and spending analysis.
"""

from decimal import Decimal
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


async def _require_auth(request: Request):
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


@router.get("/analytics")
async def analytics_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: int = None,
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    from datetime import date
    target_year = year or date.today().year
    prev_year = target_year - 1

    # Monthly spending (bar chart)
    monthly_data = []
    monthly_labels = []
    for m in range(1, 13):
        labels = []
        vals = []
        for y in [target_year, prev_year]:
            result = await db.execute(
                select(func.sum(Payment.paid_amount)).where(
                    Payment.year == y,
                    Payment.month == m,
                    Payment.status == "paid",
                )
            )
            val = result.scalar() or Decimal("0")
            vals.append(float(val))

        labels.append(month_name(m))
        monthly_labels.append(month_name(m))
        monthly_data.append({
            "label": month_name(m),
            "current": vals[0],
            "previous": vals[1],
        })

    # Spending by contractor (horizontal bar)
    result = await db.execute(
        select(
            Contractor.name,
            func.sum(Payment.paid_amount)
        )
        .join(Payment, Payment.contractor_id == Contractor.id)
        .where(Payment.year == target_year, Payment.status == "paid")
        .group_by(Contractor.id)
        .order_by(func.sum(Payment.paid_amount).desc())
    )
    contractor_totals = result.all()
    top5_contractors = [
        {"name": row[0], "total": float(row[1] or Decimal("0"))} for row in contractor_totals[:5]
    ]

    # Per-contractor monthly trend (line chart) — for each contractor
    contractors_result = await db.execute(select(Contractor).where(Contractor.is_active == True))
    contractors = contractors_result.scalars().all()

    trends = []
    for c in contractors:
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
            val = result.scalar() or Decimal("0")
            months_vals.append(float(val))
        trends.append({"name": c.name, "values": months_vals})

    # YoY comparison
    current_total = await db.execute(
        select(func.sum(Payment.paid_amount)).where(
            Payment.year == target_year, Payment.status == "paid"
        )
    )
    current_total = float(current_total.scalar() or Decimal("0"))

    prev_total = await db.execute(
        select(func.sum(Payment.paid_amount)).where(
            Payment.year == prev_year, Payment.status == "paid"
        )
    )
    prev_total = float(prev_total.scalar() or Decimal("0"))

    yoy_pct = ((current_total - prev_total) / prev_total * 100) if prev_total > 0 else 0

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "year": target_year,
        "prev_year": prev_year,
        "monthly_labels": monthly_labels,
        "monthly_current": [d["current"] for d in monthly_data],
        "monthly_previous": [d["previous"] for d in monthly_data],
        "top5_contractors": top5_contractors,
        "trends": trends,
        "current_total": current_total,
        "prev_total": prev_total,
        "yoy_pct": round(yoy_pct, 1),
        "month_name": month_name,
    })
