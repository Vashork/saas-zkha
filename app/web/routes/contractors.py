"""
Contractors route — CRUD for the contractor directory.
"""

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Contractor
from app.utils import generate_uuid

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


async def _require_auth(request: Request):
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


@router.get("/contractors")
async def contractors_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    result = await db.execute(select(Contractor).order_by(Contractor.name))
    contractors = result.scalars().all()

    return templates.TemplateResponse("contractors.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "contractors": contractors,
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
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    contractor = Contractor(
        id=generate_uuid(),
        name=name,
        slug=slug.lower().strip(),
        payment_type=payment_type,
        fixed_amount=float(fixed_amount) if fixed_amount else None,
        due_day=due_day,
        account_number=account_number or None,
        description=description or None,
        is_active=True,
    )
    db.add(contractor)
    await db.flush()

    return RedirectResponse(url="/contractors", status_code=303)


@router.post("/contractors/{contractor_id}/toggle")
async def toggle_contractor(
    contractor_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = result.scalar_one_or_none()
    if contractor:
        contractor.is_active = not contractor.is_active
        await db.flush()

    return RedirectResponse(url="/contractors", status_code=303)


@router.post("/contractors/{contractor_id}/delete")
async def delete_contractor(
    contractor_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/contractors", status_code=303)

    result = await db.execute(select(Contractor).where(Contractor.id == contractor_id))
    contractor = result.scalar_one_or_none()
    if contractor:
        await db.delete(contractor)
        await db.flush()

    return RedirectResponse(url="/contractors", status_code=303)
