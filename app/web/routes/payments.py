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
from sqlalchemy.orm import joinedload

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

    query = select(Payment).options(joinedload(Payment.contractor)).where(
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
    paid_amt = Decimal(amount.replace(",", ".").strip()) if amount else Decimal("0")

    # Check for existing payment this month/contractor
    existing = await db.execute(
        select(Payment).where(
            Payment.contractor_id == contractor_id,
            Payment.year == year,
            Payment.month == month,
        )
    )
    if existing.scalar_one_or_none():
        return templates.TemplateResponse("payments.html", {
            "request": request,
            "username": request.cookies.get("username", "User"),
            "user_role": request.cookies.get("user_role", "user"),
            "month_name": month_name(month),
            "year": year,
            "payments": [],
            "contractors": [],
            "status_filter": "",
            "payment_color_class": payment_color_class,
            "error": "Платеж за этот месяц уже существует",
        })

    # Determine due_date from contractor
    contractor_result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = contractor_result.scalar_one_or_none()
    due_day = contractor.due_day if contractor else 1
    try:
        due_date = date(year, month, due_day)
    except ValueError:
        due_date = date(year, month, 28)

    payment = Payment(
        id=f"pay-{year}{month:02d}-{contractor_id}-manual",
        contractor_id=contractor_id,
        year=year,
        month=month,
        amount=paid_amt,
        paid_amount=paid_amt if paid_date else None,
        due_date=due_date,
        paid_date=paid_date if paid_date != today else None,
        status="paid" if paid_date and paid_amt > 0 else "pending",
        receipt_file=receipt_path,
    )
    # If no paid_date given, it's pending
    if not paid_date_str:
        payment.status = "pending"
        payment.paid_amount = None
        payment.paid_date = None

    db.add(payment)
    await db.commit()

    return RedirectResponse(url="/payments", status_code=303)


@router.post("/payments/{payment_id}/edit")
async def edit_payment(
    payment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    amount: str = Form("0"),
    status: str = Form("pending"),
    paid_date_str: str = Form(""),
    receipt: UploadFile = File(None),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        return RedirectResponse(url="/payments", status_code=303)

    amount_val = Decimal(amount.replace(",", ".").strip()) if amount else Decimal("0")
    payment.amount = amount_val
    payment.status = status

    if paid_date_str:
        payment.paid_date = date.fromisoformat(paid_date_str)
        payment.paid_amount = amount_val
    else:
        payment.paid_date = None
        payment.paid_amount = None if status != "paid" else payment.paid_amount

    # Handle receipt upload
    if receipt and receipt.filename:
        if is_allowed_file(receipt.filename):
            upload_dir = get_upload_path(payment.year, payment.month, UPLOAD_DIR)
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
            payment.receipt_file = f"{payment.year}/{payment.month:02d}/{filename}"

    await db.commit()
    return RedirectResponse(url="/payments", status_code=303)


@router.post("/payments/{payment_id}/delete")
async def delete_payment(
    payment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment:
        await db.delete(payment)
        await db.commit()

    return RedirectResponse(url="/payments", status_code=303)
