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


def _as_decimal(value) -> Decimal:
    """Safely convert nullable numeric DB values to Decimal."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _requires_amount(payment: Payment) -> bool:
    """Variable payment exists, but actual bill amount has not been entered yet."""
    contractor = getattr(payment, "contractor", None)
    return (
        contractor is not None
        and contractor.payment_type == "variable"
        and payment.amount is None
        and payment.paid_amount is None
        and payment.status != "paid"
    )


def _planned_amount(payment: Payment) -> Decimal:
    """Return expected charge using the same fixed-debt rule as dashboard."""
    candidates: list[Decimal] = []
    contractor = getattr(payment, "contractor", None)
    if contractor and contractor.payment_type == "fixed" and contractor.fixed_amount is not None:
        candidates.append(_as_decimal(contractor.fixed_amount))
    if payment.amount is not None:
        candidates.append(_as_decimal(payment.amount))
    if payment.paid_amount is not None:
        candidates.append(_as_decimal(payment.paid_amount))
    return max(candidates) if candidates else Decimal("0")


def _paid_amount(payment: Payment) -> Decimal:
    return _as_decimal(payment.paid_amount)


def _remaining_amount(payment: Payment) -> Decimal:
    remaining = _planned_amount(payment) - _paid_amount(payment)
    return remaining if remaining > 0 else Decimal("0")


def _is_open_payment(payment: Payment) -> bool:
    return _remaining_amount(payment) > 0 or _requires_amount(payment)


def _effective_status(payment: Payment) -> str:
    """Return visual/business status, not just raw DB status."""
    if not _is_open_payment(payment):
        return "paid"
    if payment.status == "overdue":
        return "overdue"
    if payment.due_date and payment.due_date <= date.today():
        return "overdue"
    return "pending"


def _status_label(payment: Payment) -> str:
    status = _effective_status(payment)
    if _requires_amount(payment):
        return "ожидает начисления" if status == "pending" else "просрочено, нет суммы"
    if status == "overdue":
        return "просрочено"
    if status == "pending":
        return "к оплате"
    return "оплачено"


def _status_css_class(payment: Payment) -> str:
    status = _effective_status(payment)
    if status == "paid":
        return "paid"
    return payment_color_class(payment.due_date, status)


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
    }
    if extra:
        ctx.update(extra)
    return ctx


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
        if not is_allowed_file(receipt.filename):
            ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Недопустимый формат файла (PDF, JPG, PNG)"})
            return templates.TemplateResponse("payments.html", ctx)

        content = await receipt.read()
        if len(content) > MAX_FILE_SIZE:
            ctx = await _page_context(request, db, current_user, year=selected_year, month=selected_month, extra={"error": "Файл слишком большой (макс. 10MB)"})
            return templates.TemplateResponse("payments.html", ctx)

        upload_dir = get_upload_path(selected_year, selected_month, UPLOAD_DIR)
        ext = os.path.splitext(receipt.filename)[1]
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        receipt_path = f"{selected_year}/{selected_month:02d}/{filename}"

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
        if not is_allowed_file(receipt.filename):
            ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Недопустимый формат файла (PDF, JPG, PNG)"})
            return templates.TemplateResponse("payments.html", ctx)
        try:
            content = await receipt.read()
            if len(content) > MAX_FILE_SIZE:
                ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Файл слишком большой (макс. 10MB)"})
                return templates.TemplateResponse("payments.html", ctx)
            upload_dir = get_upload_path(payment.year, payment.month, UPLOAD_DIR)
            ext = os.path.splitext(receipt.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as f:
                f.write(content)
            _remove_receipt_file(payment.receipt_file)
            payment.receipt_file = f"{payment.year}/{payment.month:02d}/{filename}"
        except Exception as e:
            logger.error("Receipt upload error: %s", e)
            ctx = await _page_context(request, db, current_user, year=payment.year, month=payment.month, extra={"error": "Ошибка загрузки файла"})
            return templates.TemplateResponse("payments.html", ctx)

    await db.commit()
    return _redirect_to_period(payment.year, payment.month)


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
