"""
Payments route — current month payments with CRUD, filters, manual add.
"""

import os
import uuid
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Request, Form, File, UploadFile, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name, payment_color_class, is_allowed_file, get_upload_path, ALLOWED_EXTENSIONS, MAX_FILE_SIZE

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")


async def _require_auth(request: Request):
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


@router.get("/payments")
async def payments_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status_filter: str = "",
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    today = date.today()
    year, month = today.year, today.month

    query = select(Payment).options(selectinload(Payment)).where(
        Payment.year == year, Payment.month == month
    )
    if status_filter and status_filter != "all":
        query = query.where(Payment.status == status_filter)

    result = await db.execute(query)
    payments = result.scalars().all()

    # Get all contractors for the manual add form
    contractors_result = await db.execute(select(Contractor).where(Contractor.is_active == True))
    contractors = contractors_result.scalars().all()

    return templates.TemplateResponse("payments.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "month_name": month_name(month),
        "year": year,
        "payments": payments,
        "contractors": contractors,
        "status_filter": status_filter,
        "payment_color_class": payment_color_class,
    })


@router.post("/payments/add")
async def add_payment(
    request: Request,
    db: AsyncSession = Depends(get_db),
    contractor_id: str = Form(...),
    amount: str = Form("0"),
    paid_date_str: str = Form(""),
    receipt: UploadFile = File(None),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    today = date.today()
    year, month = today.year, today.month

    # Handle receipt upload
    receipt_path = None
    if receipt and receipt.filename:
        if is_allowed_file(receipt.filename):
            upload_dir = get_upload_path(year, month, UPLOAD_DIR)
            ext = os.path.splitext(receipt.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as f:
                content = await receipt.read()
                if len(content) > MAX_FILE_SIZE:
                    return templates.TemplateResponse("payments.html", {
                        "request": request,
                        "error": "Файл слишком большой (макс. 10MB)",
                    })
                f.write(content)
            receipt_path = f"{year}/{month:02d}/{filename}"

    paid_date = date.fromisoformat(paid_date_str) if paid_date_str else today
    paid_amt = Decimal(amount) if amount else Decimal("0")

    payment = Payment(
        id=f"pay-{year}{month:02d}-{contractor_id}-manual",
        contractor_id=contractor_id,
        year=year,
        month=month,
        amount=paid_amt,
        paid_amount=paid_amt,
        due_date=today,
        paid_date=paid_date,
        status="paid",
        receipt_file=receipt_path,
    )
    db.add(payment)
    await db.flush()

    return RedirectResponse(url="/payments", status_code=303)
