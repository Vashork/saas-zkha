"""
Auth routes — login, logout, session management, user management.
"""

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User
from app.utils import verify_password, hash_password

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

# Pages that exist in the app
PAGES = [
    ("dashboard", "📊 Дашборд"),
    ("payments", "💳 Платежи"),
    ("history", "📜 История"),
    ("contractors", "🏢 Подрядчики"),
    ("analytics", "📈 Аналитика"),
    ("settings", "⚙️ Настройки"),
]


@router.get("/login")
async def login_page(request: Request):
    if "user_id" in request.cookies:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user and verify_password(password, user.password_hash):
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key="user_id",
            value=str(user.id),
            httponly=True,
            max_age=7 * 24 * 60 * 60,
            samesite="lax",
        )
        response.set_cookie(key="username", value=user.username, samesite="lax")
        response.set_cookie(key="user_role", value=user.role, samesite="lax")
        # Store page permissions as comma-separated slugs
        perms = getattr(user, "page_permissions", None)
        response.set_cookie(key="page_permissions", value=perms or "", samesite="lax")
        return response

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Неверный логин или пароль",
    })


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("user_id")
    response.delete_cookie("username")
    response.delete_cookie("user_role")
    response.delete_cookie("page_permissions")
    return response


async def _require_auth(request: Request):
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


@router.get("/settings")
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "users": users,
        "pages": PAGES,
        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
    })


@router.post("/settings/change-username")
async def change_username(
    request: Request,
    db: AsyncSession = Depends(get_db),
    username: str = Form(...),
    current_password: str = Form(""),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_id = int(request.cookies.get("user_id", 0))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_password(current_password, user.password_hash):
        return RedirectResponse(url="/settings?error=Неверный+текущий+пароль", status_code=303)

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/settings?error=Имя+уже+занято", status_code=303)

    user.username = username
    await db.commit()

    response = RedirectResponse(url="/settings?success=Имя+изменено", status_code=303)
    response.set_cookie(key="username", value=username, samesite="lax")
    return response


@router.post("/settings/change-password")
async def change_password(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_id = int(request.cookies.get("user_id", 0))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_password(current_password, user.password_hash):
        return RedirectResponse(url="/settings?error=Неверный+текущий+пароль", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse(url="/settings?error=Пароли+не+совпадают", status_code=303)
    if len(new_password) < 4:
        return RedirectResponse(url="/settings?error=Минимум+4+символа", status_code=303)

    user.password_hash = hash_password(new_password)
    await db.commit()

    return RedirectResponse(url="/settings?success=Пароль+изменён", status_code=303)


@router.post("/settings/users/create")
async def create_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    # Page permissions
    page_dashboard: str = Form("off"),
    page_payments: str = Form("off"),
    page_history: str = Form("off"),
    page_contractors: str = Form("off"),
    page_analytics: str = Form("off"),
    page_settings: str = Form("off"),
    # Edit permissions
    edit_payments: str = Form("off"),
    edit_contractors: str = Form("off"),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/settings?error=Имя+уже+занято", status_code=303)

    # Build permissions
    allowed_pages = []
    for slug in ["dashboard", "payments", "history", "contractors", "analytics", "settings"]:
        if getattr(request.form, f"page_{slug}", request.form.get(f"page_{slug}", "off")) == "on":
            allowed_pages.append(slug)

    can_edit_payments = request.form.get("edit_payments") == "on"
    can_edit_contractors = request.form.get("edit_contractors") == "on"

    perms = {
        "pages": allowed_pages,
        "edit": {
            "payments": can_edit_payments,
            "contractors": can_edit_contractors,
        }
    }

    new_user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(new_user)
    await db.commit()

    return RedirectResponse(url="/settings?success=Пользователь+создан", status_code=303)


@router.post("/settings/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    # Don't allow deleting yourself
    if int(request.cookies.get("user_id", 0)) == user_id:
        return RedirectResponse(url="/settings?error=Нельзя+удалить+себя", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        await db.delete(user)
        await db.commit()

    return RedirectResponse(url="/settings?success=Пользователь+удалён", status_code=303)


@router.post("/settings/users/{user_id}/update")
async def update_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    role: str = Form("user"),
    page_dashboard: str = Form("off"),
    page_payments: str = Form("off"),
    page_history: str = Form("off"),
    page_contractors: str = Form("off"),
    page_analytics: str = Form("off"),
    page_settings: str = Form("off"),
    edit_payments: str = Form("off"),
    edit_contractors: str = Form("off"),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings", status_code=303)

    user.role = role

    # Build permissions
    allowed_pages = []
    for slug in ["dashboard", "payments", "history", "contractors", "analytics", "settings"]:
        if request.form.get(f"page_{slug}") == "on":
            allowed_pages.append(slug)

    perms = {
        "pages": allowed_pages,
        "edit": {
            "payments": request.form.get("edit_payments") == "on",
            "contractors": request.form.get("edit_contractors") == "on",
        }
    }

    # Store as JSON string in a simple format
    user.page_permissions = ",".join(allowed_pages)

    await db.commit()
    return RedirectResponse(url="/settings?success=Пользователь+обновлён", status_code=303)
