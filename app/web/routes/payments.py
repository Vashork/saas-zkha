"""
Payments route — payments with CRUD, filters, manual add, and period selector.
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
from app.utils import month_name, is_allowed_file, get_upload_path, MAX_FILE_SIZE
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
)

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





def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    """Shift a year/month pair by N months and return normalized (year, month)."""
    month_index = year * 12 + (month - 1) + offset
    return month_index // 12, month_index % 12 + 1


def _parse_period(request: Request, today: date) -> tuple[int, int]:
    """Parse selected year/month from query params with safe fallback."""
    try:
        year = int(request.query_params.get("year", today.year))
    except (TypeError, ValueError):
        year = today.year

    try:
        month = int(request.query_params.get("month", today.month))
    except (TypeError, ValueError):
        month = today.month

    if year < 2000 or year > 2100:
        year = today.year
    if month < 1 or month > 12:
        month = today.month

    return year, month


async def _build_month_options(db: AsyncSession, selected_year: int, selected_month: int, today: date):
    """Build month selector options from DB plus rolling period."""
    month_keys = {(selected_year, selected_month)}

    for offset in range(-23, 13):
        month_keys.add(_shift_month(today.year, today.month, offset))

    result = await db.execute(
        select(Payment.year, Payment.month)
        .distinct()
        .order_by(Payment.year.desc(), Payment.month.desc())
    )
    for y, m in result.all():
        if y and m and 1 <= m <= 12:
            month_keys.add((int(y), int(m)))

    return [(y, m, month_name(m)) for y, m in sorted(month_keys, reverse=True)]


def _period_url(year: int, month: int, status_filter: str = "") -> str:
    """Return payments URL preserving selected period and optional status filter."""
    url = f"/payments?year={year}&month={month}"
    if status_filter and status_filter != "all":
        url += f"&status_filter={status_filter}"
    return url


async def _page_context(
    request: Request,
    db: AsyncSession,
    current_user,
    year: int | None = None,
    month: int | None = None,
    status_filter: str = "",
    extra: dict | None = None,
):
    """Build full payments.html context, including rows, contractors and period selector."""
    today = date.today()
    if year is None or month is None:
        year, month = _parse_period(request, today)

    query = select(Payment).options(joinedload(Payment.contractor)).where(
        Payment.year == year,
        Payment.month == month,
    )

    payments_result = await db.execute(query)
    payments = payments_result.scalars().all()
    if status_filter and status_filter != "all":
        payments = [p for p in payments if _effective_status(p) == status_filter]

    contractors_result = await db.execute(select(Contractor).where(Contractor.is_active == True))
    contractors = contractors_result.scalars().all()
    month_options = await _build_month_options(db, year, month, today)

    ctx = {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "month_name": month_name(month),
        "year": year,
        "month": month,
        "payments": payments,
        "contractors": contractors,
        "status_filter": status_filter,
        "month_options": month_options,
        "payment_color_class": payment_color_class,
        "period_url": _period_url,
        "planned_amount": _planned_amount,
        "paid_amount": _paid_amount,
        "remaining_amount": _remaining_amount,
        "requires_amount": _requires_amount,
        "effective_status": _effective_status,
        "status_label": _status_label,
        "status_css_class": _status_css_class,
        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
        "removed_receipts": request.query_params.get("removed_receipts", "0"),
    }
    if extra:
        ctx.update(extra)
    return ctx


async def _upload_receipt(
    receipt: UploadFile,
    year: int,
    month: int,
) -> tuple[str | None, str | None]:
    """Validate and save an uploaded receipt file.

    Returns (receipt_path, error_message).
    If no file or valid upload, error_message is None.
    """
    if not receipt or not receipt.filename:
        return None, None

    if not is_allowed_file(receipt.filename):
        return None, "Недопустимый формат файла (PDF, JPG, PNG)"

    content = await receipt.read()
    if len(content) > MAX_FILE_SIZE:
        return None, "Файл слишком большой (макс. 10MB)"

    upload_dir = get_upload_path(year, month, UPLOAD_DIR)
    ext = os.path.splitext(receipt.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(upload_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    return f"{year}/{month:02d}/{filename}", None


def _parse_amount(raw: str) -> Decimal:
    value = (raw or "0").replace(",", ".").strip()
    return Decimal(value) if value else Decimal("0")


def _new_payment_amount(contractor: Contractor, raw_amount: str, status: str) -> Decimal | None:
    """Parse amount for manual payment creation and allow blank variable bills."""
    value = (raw_amount or "").strip()
    if not value:
        if contractor.payment_type == "variable" and status != "paid":
            return None
        if contractor.payment_type == "fixed" and contractor.fixed_amount is not None:
            return _as_decimal(contractor.fixed_amount)
    return _parse_amount(raw_amount)


def _redirect_to_period(year: int, month: int, status_filter: str = "") -> RedirectResponse:
    return RedirectResponse(url=_period_url(year, month, status_filter), status_code=303)


def _receipt_path(receipt_file: str | None) -> str | None:
    """Build a safe absolute path for a stored receipt file."""
    if not receipt_file:
        return None
    normalized = os.path.normpath(receipt_file)
    if os.path.isabs(normalized) or normalized.startswith(".."):
        return None
    base_dir = os.path.abspath(UPLOAD_DIR)
    full_path = os.path.abspath(os.path.join(base_dir, normalized))
    if not full_path.startswith(base_dir + os.sep):
        return None
    return full_path


def _remove_receipt_file(receipt_file: str | None) -> None:
    """Remove a receipt file from uploads if it belongs to the local uploads tree."""
    path = _receipt_path(receipt_file)
    if not path or not os.path.isfile(path):
        return
    try:
        os.remove(path)
    except OSError as exc:
        logger.warning("Could not remove receipt file %s: %s", path, exc)


def _normalize_receipt_ref(path: str) -> str:
    return os.path.normpath(path).replace(os.sep, "/")


def _cleanup_orphan_receipts(referenced_receipts: set[str]) -> int:
    """Remove files in uploads/ that are not referenced by any payment."""
    base_dir = os.path.abspath(UPLOAD_DIR)
    if not os.path.isdir(base_dir):
        return 0

    removed = 0
    for root, _, files in os.walk(base_dir):
        for filename in files:
            full_path = os.path.abspath(os.path.join(root, filename))
            if not full_path.startswith(base_dir + os.sep):
                continue
            rel_path = _normalize_receipt_ref(os.path.relpath(full_path, base_dir))
            if rel_path in referenced_receipts:
                continue
            try:
                os.remove(full_path)
                removed += 1
            except OSError as exc:
                logger.warning("Could not remove orphan receipt %s: %s", full_path, exc)
    return removed


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

    today = date.today()
    year, month = _parse_period(request, today)

    return templates.TemplateResponse(
        "payments.html",
        await _page_context(request, db, current_user, year=year, month=month, status_filter=status_filter),
    )


@router.post("/payments/add")
async def add_payment(
    request: Request,
    db: AsyncSession = Depends(get_db),
    contractor_id: str = Form(...),
    amount: str = Form(""),
    status: str = Form("pending"),
    paid_date_str: str = Form(""),
    year: int = Form(None),
    month: int = Form(None),
    receipt: UploadFile = File(None),
):
    current_user, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    today = date.today()
    selected_year = year if year and 2000 <= year <= 2100 else today.year
    selected_month = month if month and 1 <= month <= 12 else today.month

    if status not in {"pending", "paid", "overdue"}:
        ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Некорректный статус"})
        return templates.TemplateResponse("payments.html", ctx)

    existing = await db.execute(
        select(Payment).where(
            Payment.contractor_id == contractor_id,
            Payment.year == selected_year,
            Payment.month == selected_month,
        )
    )
    if existing.scalar_one_or_none():
        ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Платеж за этот месяц уже существует"})
        return templates.TemplateResponse("payments.html", ctx)

    contractor_result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = contractor_result.scalar_one_or_none()
    if not contractor:
        ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Подрядчик не найден"})
        return templates.TemplateResponse("payments.html", ctx)

    try:
        paid_amt = _new_payment_amount(contractor, amount, status)
    except (InvalidOperation, ValueError):
        ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Некорректная сумма"})
        return templates.TemplateResponse("payments.html", ctx)

    if status == "paid" and paid_amt is None:
        ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Для оплаты нужно указать сумму начисления"})
        return templates.TemplateResponse("payments.html", ctx)

    receipt_path = None
    if receipt and receipt.filename:
        receipt_path, upload_err = await _upload_receipt(receipt, selected_year, selected_month)
        if upload_err:
            ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": upload_err})
            return templates.TemplateResponse("payments.html", ctx)

    paid_date = None
    if paid_date_str:
        try:
            paid_date = date.fromisoformat(paid_date_str)
        except ValueError:
            ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Некорректная дата оплаты"})
            return templates.TemplateResponse("payments.html", ctx)

    due_day = min(contractor.due_day, 28)
    due_date = date(selected_year, selected_month, due_day)

    paid_amount = None
    if status == "paid":
        paid_amount = paid_amt
        if not paid_date:
            paid_date = today
    else:
        paid_date = None

    payment = Payment(
        id=f"pay-{selected_year}{selected_month:02d}-{contractor_id}-{uuid.uuid4().hex[:8]}",
        contractor_id=contractor_id,
        year=selected_year,
        month=selected_month,
        amount=paid_amt,
        paid_amount=paid_amount,
        due_date=due_date,
        paid_date=paid_date,
        status=status,
        receipt_file=receipt_path,
    )
    db.add(payment)
    await db.commit()

    return _redirect_to_period(selected_year, selected_month)


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
            ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Некорректная сумма"})
            return templates.TemplateResponse("payments.html", ctx)

    if status:
        if status not in {"pending", "paid", "overdue"}:
            ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Некорректный статус"})
            return templates.TemplateResponse("payments.html", ctx)
        payment.status = status

    if status == "paid":
        if payment.amount is None:
            ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Для оплаты нужно указать сумму начисления"})
            return templates.TemplateResponse("payments.html", ctx)
        if paid_date_str:
            try:
                payment.paid_date = date.fromisoformat(paid_date_str)
            except ValueError:
                ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Некорректная дата оплаты"})
                return templates.TemplateResponse("payments.html", ctx)
        elif not payment.paid_date:
            payment.paid_date = date.today()
        payment.paid_amount = payment.amount
    elif status in {"pending", "overdue"}:
        payment.paid_date = None
        payment.paid_amount = None
    elif paid_date_str:
        try:
            payment.paid_date = date.fromisoformat(paid_date_str)
        except ValueError:
            ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Некорректная дата оплаты"})
            return templates.TemplateResponse("payments.html", ctx)

    if receipt and receipt.filename:
        new_receipt_path, upload_err = await _upload_receipt(receipt, payment.year, payment.month)
        if upload_err:
            ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": upload_err})
            return templates.TemplateResponse("payments.html", ctx)
        _remove_receipt_file(payment.receipt_file)
        payment.receipt_file = new_receipt_path

    await db.commit()
    return _redirect_to_period(payment.year, payment.month)


@router.post("/payments/cleanup-receipts")
async def cleanup_orphan_receipts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: int = Form(None),
    month: int = Form(None),
    status_filter: str = Form(""),
):
    _, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    today = date.today()
    selected_year = year if year and 2000 <= year <= 2100 else today.year
    selected_month = month if month and 1 <= month <= 12 else today.month

    refs_result = await db.execute(select(Payment.receipt_file).where(Payment.receipt_file.is_not(None)))
    referenced_receipts = {
        _normalize_receipt_ref(receipt_file)
        for receipt_file in refs_result.scalars().all()
        if receipt_file
    }
    removed_count = _cleanup_orphan_receipts(referenced_receipts)

    url = _period_url(selected_year, selected_month, status_filter)
    url += f"&success=orphan_receipts_removed&removed_receipts={removed_count}"
    return RedirectResponse(url=url, status_code=303)


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
        year, month = payment.year, payment.month
        _remove_receipt_file(payment.receipt_file)
        await db.delete(payment)
        await db.commit()
        return _redirect_to_period(year, month)

    return RedirectResponse(url="/payments", status_code=303)
