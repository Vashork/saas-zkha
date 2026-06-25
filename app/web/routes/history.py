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
from app.web.routes.auth import _require_page, get_current_user
from app.web.routes.payment_helpers import (
    _as_decimal,
    _requires_amount,
    _planned_amount,
    _paid_amount,
    _remaining_amount,
    _effective_status,
    _status_label,
    _status_css_class,
    _filter_by_effective_status,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def _history_query(year: int | None, month: int | None, contractor_id: str = ""):
    query = select(Payment).options(joinedload(Payment.contractor))
    if year:
        query = query.where(Payment.year == year)
    if month:
        query = query.where(Payment.month == month)
    if contractor_id:
        query = query.where(Payment.contractor_id == contractor_id)
    return query.order_by(Payment.due_date.desc())


@router.get("/history")
async def history_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: int = Query(None),
    month: int = Query(None),
    contractor_id: str = Query(""),
    status_filter: str = Query(""),
):
    redirect = await _require_page(request, "history")
    if redirect:
        return redirect

    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(_history_query(year, month, contractor_id))
    payments = _filter_by_effective_status(result.scalars().all(), status_filter)

    contractors_result = await db.execute(select(Contractor))
    contractors = contractors_result.scalars().all()

    years_result = await db.execute(select(Payment.year).distinct().order_by(Payment.year.desc()))
    years = [row[0] for row in years_result.all()]

    return templates.TemplateResponse("history.html", {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "payments": payments,
        "contractors": contractors,
        "years": years,
        "selected_year": year,
        "selected_month": month,
        "selected_contractor": contractor_id,
        "status_filter": status_filter,
        "month_name": month_name,
        "payment_color_class": payment_color_class,
        "planned_amount": _planned_amount,
        "paid_amount": _paid_amount,
        "remaining_amount": _remaining_amount,
        "requires_amount": _requires_amount,
        "effective_status": _effective_status,
        "status_label": _status_label,
        "status_css_class": _status_css_class,
    })


@router.get("/history/export.csv")
async def export_csv(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: int = Query(None),
    month: int = Query(None),
    contractor_id: str = Query(""),
    status_filter: str = Query(""),
):
    redirect = await _require_page(request, "history")
    if redirect:
        return redirect

    result = await db.execute(_history_query(year, month, contractor_id))
    payments = _filter_by_effective_status(result.scalars().all(), status_filter)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Подрядчик", "Год", "Месяц", "Сумма", "Оплачено", "Остаток", "Срок", "Статус", "Дата оплаты"])

    for p in payments:
        writer.writerow([
            p.contractor.name if p.contractor else "",
            p.year,
            month_name(p.month),
            str(_planned_amount(p)) if _planned_amount(p) else "требуется сумма" if _requires_amount(p) else "",
            str(_paid_amount(p)) if _paid_amount(p) else "",
            str(_remaining_amount(p)) if _remaining_amount(p) else "требуется начисление" if _requires_amount(p) else "",
            str(p.due_date),
            _effective_status(p),
            str(p.paid_date) if p.paid_date else "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments_history.csv"},
    )
