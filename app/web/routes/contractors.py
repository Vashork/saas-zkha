"""
Contractors route — CRUD for the contractor directory.
"""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Contractor, Payment
from app.utils import generate_uuid
from app.web.routes.auth import _require_page, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


async def _require_admin_user(request: Request, db: AsyncSession):
    """Return active admin user or a redirect response."""
    current_user = await get_current_user(request, db)
    if not current_user:
        return None, RedirectResponse(url="/login", status_code=303)
    if current_user.role != "admin":
        return current_user, RedirectResponse(url="/contractors?error=Только+для+админа", status_code=303)
    return current_user, None


def _user_context(current_user):
    """Template identity context based on DB user, not display cookies."""
    return {
        "username": current_user.username,
        "user_role": current_user.role,
    }


def _parse_fixed_amount(payment_type: str, fixed_amount: str) -> Decimal | None:
    """Parse fixed contractor amount without float rounding."""
    if payment_type == "variable":
        return None

    raw_value = (fixed_amount or "0").replace(",", ".").strip()
    try:
        parsed = Decimal(raw_value or "0")
    except InvalidOperation:
        raise ValueError("Некорректная сумма")

    if parsed < 0:
        raise ValueError("Сумма не может быть отрицательной")

    return parsed.quantize(Decimal("0.01"))


def _contractor_error(message: str, archived: bool = False) -> RedirectResponse:
    archive_param = "&archived=1" if archived else ""
    return RedirectResponse(url=f"/contractors?error={message.replace(' ', '+')}{archive_param}", status_code=303)


def _contractors_url(archived: bool = False) -> str:
    return "/contractors?archived=1" if archived else "/contractors"


@router.get("/contractors")
async def contractors_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect = await _require_page(request, "contractors")
    if redirect:
        return redirect

    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    show_archived = request.query_params.get("archived") == "1"
    result = await db.execute(
        select(Contractor)
        .where(Contractor.is_active == (not show_archived))
        .order_by(Contractor.name)
    )
    contractors = result.scalars().all()

    return templates.TemplateResponse("contractors.html", {
        "request": request,
        **_user_context(current_user),
        "contractors": contractors,
        "show_archived": show_archived,
        "error": request.query_params.get("error"),
    })


@router.post("/contractors/add")
async def add_contractor(
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    slug: str = Form(...),
    payment_type: str = Form(...),
    fixed_amount: str = Form("0"),
    due_day: int = Form(...),
    account_number: str = Form(""),
    description: str = Form(""),
):
    current_user, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    if payment_type not in {"fixed", "variable"}:
        return _contractor_error("Некорректный тип платежа")
    if due_day < 1 or due_day > 31:
        return _contractor_error("Некорректный день оплаты")

    try:
        parsed_fixed_amount = _parse_fixed_amount(payment_type, fixed_amount)
    except ValueError as exc:
        return _contractor_error(str(exc))

    contractor = Contractor(
        id=generate_uuid(),
        name=name.strip(),
        slug=slug.lower().strip(),
        payment_type=payment_type,
        fixed_amount=parsed_fixed_amount,
        due_day=due_day,
        account_number=account_number or None,
        description=description or None,
        is_active=True,
    )
    db.add(contractor)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(Contractor)
            .where(Contractor.is_active == True)
            .order_by(Contractor.name)
        )
        contractors = result.scalars().all()
        return templates.TemplateResponse("contractors.html", {
            "request": request,
            **_user_context(current_user),
            "contractors": contractors,
            "show_archived": False,
            "error": "Конфликт: подрядчик с таким именем или slug уже существует",
        })

    return RedirectResponse(url="/contractors", status_code=303)


@router.post("/contractors/{contractor_id}/toggle")
async def toggle_contractor(
    contractor_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = result.scalar_one_or_none()
    if contractor:
        contractor.is_active = not contractor.is_active
        await db.commit()
        return RedirectResponse(url=_contractors_url(archived=not contractor.is_active), status_code=303)

    return RedirectResponse(url="/contractors", status_code=303)


@router.post("/contractors/{contractor_id}/delete")
async def delete_contractor(
    contractor_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    show_archived = request.query_params.get("archived") == "1"
    result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = result.scalar_one_or_none()
    if not contractor:
        return RedirectResponse(url=_contractors_url(show_archived), status_code=303)

    existing_payment_id = await db.scalar(
        select(Payment.id).where(Payment.contractor_id == contractor_id).limit(1)
    )
    if existing_payment_id:
        contractor.is_active = False
        await db.commit()
        return _contractor_error("У подрядчика есть платежи. Он перенесён в архив", archived=True)

    await db.delete(contractor)
    await db.commit()

    return RedirectResponse(url=_contractors_url(show_archived), status_code=303)


@router.post("/contractors/{contractor_id}/edit")
async def edit_contractor(
    contractor_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    payment_type: str = Form(...),
    fixed_amount: str = Form("0"),
    due_day: str = Form("1"),
    account_number: str = Form(""),
    description: str = Form(""),
):
    _, redirect = await _require_admin_user(request, db)
    if redirect:
        return redirect

    if payment_type not in {"fixed", "variable"}:
        return _contractor_error("Некорректный тип платежа")

    try:
        parsed_due_day = int(due_day)
    except ValueError:
        return _contractor_error("Некорректный день оплаты")
    if parsed_due_day < 1 or parsed_due_day > 31:
        return _contractor_error("Некорректный день оплаты")

    try:
        parsed_fixed_amount = _parse_fixed_amount(payment_type, fixed_amount)
    except ValueError as exc:
        return _contractor_error(str(exc))

    result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = result.scalar_one_or_none()
    if not contractor:
        return RedirectResponse(url="/contractors", status_code=303)

    contractor.name = name.strip()
    contractor.payment_type = payment_type
    contractor.fixed_amount = parsed_fixed_amount
    contractor.due_day = parsed_due_day
    contractor.account_number = account_number or None
    contractor.description = description or None

    await db.commit()
    return RedirectResponse(url=_contractors_url(archived=not contractor.is_active), status_code=303)
