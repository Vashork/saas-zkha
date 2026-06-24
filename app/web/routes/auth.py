"""
Auth routes — login, logout, session management, user management.
"""

import logging
from fastapi import APIRouter, Request, Form, Depends, Body
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db, async_session_factory
from app.models import User
from app.utils import verify_password, hash_password

logger = logging.getLogger("zhkh.auth")

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

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
    """Check that user is logged in."""
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


async def _require_page(request: Request, page_slug: str):
    """Check that user is logged in AND has permission to view the given page.
    Admins always have access to all pages.
    """
    if not request.cookies.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)

    user_role = request.cookies.get("user_role", "user")
    if user_role == "admin":
        return None

    perms_cookie = request.cookies.get("page_permissions", "")
    if not perms_cookie:
        # No permissions set means full access (legacy users)
        return None

    allowed = [p.strip() for p in perms_cookie.split(",") if p.strip()]
    if page_slug not in allowed:
        return RedirectResponse(url="/?denied=1", status_code=303)

    return None


@router.get("/settings")
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()

    # Get system settings
    from app.models import Setting as SettingModel
    settings_result = await db.execute(select(SettingModel))
    settings_dict = {s.key: s.value for s in settings_result.scalars().all()}

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "users": users,
        "pages": PAGES,
        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
        "settings": settings_dict,
        "user_theme": settings_dict.get("ui_theme", "dark"),
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
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form("user"),
    page_dashboard: str = Form("off"),
    page_payments: str = Form("off"),
    page_history: str = Form("off"),
    page_contractors: str = Form("off"),
    page_analytics: str = Form("off"),
    page_settings: str = Form("off"),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/settings?error=Только для админа", status_code=303)

    if not username.strip():
        return RedirectResponse(url="/settings?error=Имя не может быть пустым", status_code=303)
    if len(password) < 4:
        return RedirectResponse(url="/settings?error=Минимум 4 символа", status_code=303)

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/settings?error=Имя уже занято", status_code=303)

    # Build page permissions from explicit Form parameters
    perms_map = {
        "dashboard": page_dashboard,
        "payments": page_payments,
        "history": page_history,
        "contractors": page_contractors,
        "analytics": page_analytics,
        "settings": page_settings,
    }
    allowed_pages = [slug for slug, val in perms_map.items() if val == "on"]
    perms_str = ",".join(allowed_pages)

    new_user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        page_permissions=perms_str,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()

    return RedirectResponse(url="/settings?success=Пользователь создан", status_code=303)


@router.post("/settings/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Deactivate or reactivate a user (soft delete)."""
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/settings?error=Только для админа", status_code=303)

    my_id = int(request.cookies.get("user_id", 0))
    if my_id == user_id:
        return RedirectResponse(url="/settings?error=Нельзя деактивировать себя", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь не найден", status_code=303)

    # Cannot deactivate the last active admin
    if user.role == "admin" and user.is_active:
        admin_count = await db.execute(
            select(func.count(User.id)).where(
                User.role == "admin",
                User.is_active == True,
            )
        )
        if admin_count.scalar() <= 1:
            return RedirectResponse(url="/settings?error=Нельзя деактивировать последнего админа", status_code=303)

    user.is_active = not user.is_active
    await db.commit()

    action = "деактивирован" if not user.is_active else "активирован"
    return RedirectResponse(url=f"/settings?success=Пользователь {action}", status_code=303)


@router.post("/settings/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a user."""
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    my_id = int(request.cookies.get("user_id", 0))
    if my_id == user_id:
        return RedirectResponse(url="/settings?error=Нельзя+удалить+себя", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    # Cannot delete the last active admin
    if user.role == "admin" and user.is_active:
        admin_count = await db.execute(
            select(func.count(User.id)).where(
                User.role == "admin",
                User.is_active == True,
            )
        )
        if admin_count.scalar() <= 1:
            return RedirectResponse(url="/settings?error=Нельзя+удалить+последнего+админа", status_code=303)

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

    # Build page permissions from explicit Form parameters
    perms_map = {
        "dashboard": page_dashboard,
        "payments": page_payments,
        "history": page_history,
        "contractors": page_contractors,
        "analytics": page_analytics,
        "settings": page_settings,
    }
    allowed_pages = [slug for slug, val in perms_map.items() if val == "on"]
    user.page_permissions = ",".join(allowed_pages) if allowed_pages else None

    await db.commit()
    return RedirectResponse(url="/settings?success=Пользователь+обновлён", status_code=303)


@router.post("/settings/save")
async def save_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    default_due_day: str = Form("15"),
    notifications_enabled: str = Form("off"),
    theme: str = Form("dark"),
):
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    from app.models import Setting as SettingModel

    async def _upsert(key: str, value: str, description: str):
        result = await db.execute(select(SettingModel).where(SettingModel.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            db.add(SettingModel(key=key, value=value, description=description))

    await _upsert("default_due_day", default_due_day, "День платежа по умолчанию (1-28)")
    await _upsert("notifications_enabled", "on" if notifications_enabled == "on" else "off", "Включить уведомления")
    await _upsert("theme", theme, "Тема оформления: dark / light")

    await db.commit()
    return RedirectResponse(url="/settings?success=Настройки+сохранены", status_code=303)


@router.post("/settings/theme")
async def change_theme(request: Request, data: dict = Body(...)):
    """AJAX endpoint to save theme preference."""
    if not request.cookies.get("user_id"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from app.models import Setting as SettingModel
    theme_val = data.get("theme", "dark")

    async with async_session_factory() as db:
        result = await db.execute(select(SettingModel).where(SettingModel.key == "ui_theme"))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = theme_val
        else:
            db.add(SettingModel(key="ui_theme", value=theme_val, description="Тема интерфейса"))
        await db.commit()

    return JSONResponse({"ok": True})


@router.post("/settings/users/{user_id}/change-password")
async def change_user_password(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    new_password: str = Form(...),
):
    """Admin changes another user's password."""
    redirect = await _require_auth(request)
    if redirect:
        return redirect

    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    user.password_hash = hash_password(new_password)
    await db.commit()
    return RedirectResponse(url="/settings?success=Пароль+изменён", status_code=303)
