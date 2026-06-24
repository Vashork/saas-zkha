"""
History route — all payments, filters, CSV export.
"""

import csv
import io
from datetime import date
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name, payment_color_class

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


async def _require_auth(request: Request):
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


@router.get("/history")
async def history_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: int = Query(None),
    month: int = Query(None),
    contractor_id: str = Query(""),
    status_filter: str = Query(""),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    query = select(Payment).options(joinedload(Payment.contractor))

    if year:
        query = query.where(Payment.year == year)
    if month:
        query = query.where(Payment.month == month)
    if contractor_id:
        query = query.where(Payment.contractor_id == contractor_id)
    if status_filter and status_filter != "all":
        query = query.where(Payment.status == status_filter)

    query = query.order_by(Payment.due_date.desc())

    result = await db.execute(query)
    payments = result.scalars().all()

    # Get contractors for filter dropdown
    contractors_result = await db.execute(select(Contractor))
    contractors = contractors_result.scalars().all()

    # Get distinct years for filter
    years_result = await db.execute(select(Payment.year).distinct().order_by(Payment.year.desc()))
    years = [row[0] for row in years_result.all()]

    return templates.TemplateResponse("history.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "payments": payments,
        "contractors": contractors,
        "years": years,
        "selected_year": year,
        "selected_month": month,
        "selected_contractor": contractor_id,
        "status_filter": status_filter,
        "month_name": month_name,
        "payment_color_class": payment_color_class,
    })


@router.get("/history/export.csv")
async def export_csv(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: int = Query(None),
    month: int = Query(None),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    query = select(Payment).options(joinedload(Payment.contractor))
    if year:
        query = query.where(Payment.year == year)
    if month:
        query = query.where(Payment.month == month)
    query = query.order_by(Payment.due_date.desc())

    result = await db.execute(query)
    payments = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Подрядчик", "Год", "Месяц", "Сумма", "Оплачено", "Срок", "Статус", "Дата оплаты"])

    for p in payments:
        writer.writerow([
            p.contractor.name if p.contractor else "",
            p.year,
            month_name(p.month),
            str(p.amount) if p.amount else "",
            str(p.paid_amount) if p.paid_amount else "",
            str(p.due_date),
            p.status,
            str(p.paid_date) if p.paid_date else "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments_history.csv"},
    )
