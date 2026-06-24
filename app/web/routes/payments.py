"""
Payments route — current month payments with CRUD, filters, manual add.
"""

import os
import uuid
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Form, File, UploadFile, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Payment, Contractor
from app.utils import month_name, payment_color_class, is_allowed_file, get_upload_path, MAX_FILE_SIZE
from app.web.routes.auth import _require_page, get_current_user

logger = logging.getLogger("zhkh.payments")

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")


async def _require_admin_user(request: Request, db: AsyncSession):
    """Return active admin user or a redirect response."""
    current_user = await get_current_user(request, db)
    if not current_user:
        return None, RedirectResponse(url="/login", status_code=303)
    if current_user.role != "admin":
        return current_user, RedirectResponse(url="/payments?error=Только+для+админа", status_code=303)
    return current_user, None


async def _page_context(
    request: Request,
    db: AsyncSession,
    current_user,
    status_filter: str = "",
    extra: dict | None = None,
):
    """Build full payments.html context, including rows and contractors."""
    today = date.today()
    year, month = today.year, today.month

    query = select(Payment).options(joinedload(Payment.contractor)).where(
        Payment.year == year,
        Payment.month == month,
    )
    if status_filter and status_filter != "all":
        query = query.where(Payment.status == status_filter)

    payments_result = await db.execute(query)
    payments = payments_result.scalars().all()

    contractors_result = await db.execute(select(Contractor).where(Contractor.is_active == True))
    contractors = contractors_result.scalars().all()

    ctx = {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "month_name": month_name(month),
        "year": year,
        "payments": payments,
        "contractors": contractors,
        "status_filter": status_filter,
        "payment_color_class": payment_color_class,
        "error": request.query_params.get("error"),
    }
    if extra:
        ctx.update(extra)
    return ctx


def _parse_amount(raw: str) -> Decimal:
    value = (raw or "0").replace(",", ".").strip()
    return Decimal(value) if value else Decimal("0")


@router.get("/payments")
async def payments_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status_filter: str = "",
):
    redirect = await _require_page(request, "payments")
    if redirect:
        return redirect

    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(
        "payments.html",
        await _page_context(request, db, current_user, status_filter=status_filter),
    )


@router.post("/payments/add")
async def add_payment(
    request: Request,
    db: AsyncSession = Depends(get_db),
    contractor_id: str = Form(...),
    amount: str = Form("0"),
    paid_date_str: str = Form(""),
    receipt: UploadFile = File(None),
):
    current_user, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    today = date.today()
    year, month = today.year, today.month

    try:
        paid_amt = _parse_amount(amount)
    except (InvalidOperation, ValueError):
        ctx = await _page_context(request, db, current_user, extra={"error": "Некорректная сумма"})
        return templates.TemplateResponse("payments.html", ctx)

    receipt_path = None
    if receipt and receipt.filename:
        if not is_allowed_file(receipt.filename):
            ctx = await _page_context(request, db, current_user, extra={"error": "Недопустимый формат файла (PDF, JPG, PNG)"})
            return templates.TemplateResponse("payments.html", ctx)

        content = await receipt.read()
        if len(content) > MAX_FILE_SIZE:
            ctx = await _page_context(request, db, current_user, extra={"error": "Файл слишком большой (макс. 10MB)"})
            return templates.TemplateResponse("payments.html", ctx)

        upload_dir = get_upload_path(year, month, UPLOAD_DIR)
        ext = os.path.splitext(receipt.filename)[1]
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        receipt_path = f"{year}/{month:02d}/{filename}"

    paid_date = None
    if paid_date_str:
        try:
            paid_date = date.fromisoformat(paid_date_str)
        except ValueError:
            ctx = await _page_context(request, db, current_user, extra={"error": "Некорректная дата оплаты"})
            return templates.TemplateResponse("payments.html", ctx)

    existing = await db.execute(
        select(Payment).where(
            Payment.contractor_id == contractor_id,
            Payment.year == year,
            Payment.month == month,
        )
    )
    if existing.scalar_one_or_none():
        ctx = await _page_context(request, db, current_user, extra={"error": "Платеж за этот месяц уже существует"})
        return templates.TemplateResponse("payments.html", ctx)

    contractor_result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = contractor_result.scalar_one_or_none()
    if not contractor:
        ctx = await _page_context(request, db, current_user, extra={"error": "Подрядчик не найден"})
        return templates.TemplateResponse("payments.html", ctx)

    due_day = min(contractor.due_day, 28)
    due_date = date(year, month, due_day)
    status = "paid" if paid_date and paid_amt > 0 else "pending"

    payment = Payment(
        id=f"pay-{year}{month:02d}-{contractor_id}-{uuid.uuid4().hex[:8]}",
        contractor_id=contractor_id,
        year=year,
        month=month,
        amount=paid_amt,
        paid_amount=paid_amt if status == "paid" else None,
        due_date=due_date,
        paid_date=paid_date,
        status=status,
        receipt_file=receipt_path,
    )
    db.add(payment)
    await db.commit()

    return RedirectResponse(url="/payments", status_code=303)


@router.post("/payments/{payment_id}/edit")
async def edit_payment(
    payment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    amount: str = Form(""),
    status: str = Form(""),
    paid_date_str: str = Form(""),
    receipt: UploadFile = File(None),
):
    current_user, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        return RedirectResponse(url="/payments", status_code=303)

    if amount.strip():
        try:
            payment.amount = _parse_amount(amount)
        except (InvalidOperation, ValueError):
            ctx = await _page_context(request, db, current_user, extra={"error": "Некорректная сумма"})
            return templates.TemplateResponse("payments.html", ctx)

    if status:
        if status not in {"pending", "paid", "overdue"}:
            ctx = await _page_context(request, db, current_user, extra={"error": "Некорректный статус"})
            return templates.TemplateResponse("payments.html", ctx)
        payment.status = status

    if paid_date_str:
        try:
            payment.paid_date = date.fromisoformat(paid_date_str)
        except ValueError:
            ctx = await _page_context(request, db, current_user, extra={"error": "Некорректная дата оплаты"})
            return templates.TemplateResponse("payments.html", ctx)
        payment.paid_amount = payment.amount
    elif status == "paid":
        payment.paid_date = date.today()
        payment.paid_amount = payment.amount

    if receipt and receipt.filename:
        if not is_allowed_file(receipt.filename):
            ctx = await _page_context(request, db, current_user, extra={"error": "Недопустимый формат файла (PDF, JPG, PNG)"})
            return templates.TemplateResponse("payments.html", ctx)
        try:
            content = await receipt.read()
            if len(content) > MAX_FILE_SIZE:
                ctx = await _page_context(request, db, current_user, extra={"error": "Файл слишком большой (макс. 10MB)"})
                return templates.TemplateResponse("payments.html", ctx)
            upload_dir = get_upload_path(payment.year, payment.month, UPLOAD_DIR)
            ext = os.path.splitext(receipt.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as f:
                f.write(content)
            payment.receipt_file = f"{payment.year}/{payment.month:02d}/{filename}"
        except Exception as e:
            logger.error("Receipt upload error: %s", e)
            ctx = await _page_context(request, db, current_user, extra={"error": "Ошибка загрузки файла"})
            return templates.TemplateResponse("payments.html", ctx)

    await db.commit()
    return RedirectResponse(url="/payments", status_code=303)


@router.post("/payments/{payment_id}/delete")
async def delete_payment(
    payment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment:
        await db.delete(payment)
        await db.commit()

    return RedirectResponse(url="/payments", status_code=303)
