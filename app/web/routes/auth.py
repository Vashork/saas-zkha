"""
Auth routes — login, logout, session management, user management.
"""

import base64
import hashlib
import hmac
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Request, Form, Depends, Body
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, async_session_factory
from app.models import User
from app.utils import verify_password, hash_password

logger = logging.getLogger("zhkh.auth")

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

SESSION_COOKIE = "session"
LEGACY_COOKIES = ("user_id", "username", "user_role", "page_permissions")
SESSION_BOOT_ID = secrets.token_urlsafe(32)

PAGES = [
    ("dashboard", "📊 Дашборд"),
    ("payments", "💳 Платежи"),
    ("history", "📜 История"),
    ("contractors", "🏢 Подрядчики"),
    ("analytics", "📈 Аналитика"),
    ("settings", "⚙️ Настройки"),
]


def _session_secret() -> bytes:
    """Session secret includes a per-process boot id, so restart invalidates sessions."""
    base_secret = get_settings().SECRET_KEY
    return f"{base_secret}:{SESSION_BOOT_ID}".encode("utf-8")


def _sign_user_id(user_id: int) -> str:
    """Create a signed session cookie value for the user id."""
    payload = str(user_id).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii")
    signature = hmac.new(_session_secret(), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def _verify_session_cookie(value: str | None) -> Optional[int]:
    """Return user id from a signed session cookie, or None if invalid."""
    if not value or "." not in value:
        return None
    payload_b64, signature = value.rsplit(".", 1)
    expected = hmac.new(_session_secret(), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        decoded = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        return int(decoded)
    except (ValueError, UnicodeDecodeError):
        return None


def _login_redirect(request: Request) -> RedirectResponse:
    """Redirect unauthenticated users to login. Login always returns to dashboard."""
    return RedirectResponse(url="/login", status_code=303)


def _set_session_cookies(response: RedirectResponse, user: User) -> None:
    max_age = 7 * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE,
        value=_sign_user_id(user.id),
        httponly=True,
        max_age=max_age,
        samesite="lax",
    )
    # Display-only legacy cookies. Authorization never trusts them.
    response.set_cookie(key="user_id", value=str(user.id), httponly=True, max_age=max_age, samesite="lax")
    response.set_cookie(key="username", value=user.username, httponly=True, max_age=max_age, samesite="lax")
    response.set_cookie(key="user_role", value=user.role, httponly=True, max_age=max_age, samesite="lax")
    response.set_cookie(
        key="page_permissions",
        value=getattr(user, "page_permissions", None) or "",
        httponly=True,
        max_age=max_age,
        samesite="lax",
    )


def _clear_session_cookies(response: RedirectResponse) -> None:
    response.delete_cookie(SESSION_COOKIE)
    for cookie_name in LEGACY_COOKIES:
        response.delete_cookie(cookie_name)


async def get_current_user(request: Request, db: AsyncSession) -> Optional[User]:
    """Load the active user from the signed session cookie."""
    user_id = _verify_session_cookie(request.cookies.get(SESSION_COOKIE))
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    return result.scalar_one_or_none()


async def _load_current_user(request: Request) -> Optional[User]:
    """Load active user using a short-lived DB session for route guards."""
    async with async_session_factory() as db:
        return await get_current_user(request, db)


async def _require_auth(request: Request):
    """Check that an active user is logged in."""
    user = await _load_current_user(request)
    if not user:
        return _login_redirect(request)
    return None


async def _require_admin(request: Request):
    """Check that an active admin is logged in."""
    user = await _load_current_user(request)
    if not user:
        return _login_redirect(request)
    if user.role != "admin":
        return RedirectResponse(url="/?denied=1", status_code=303)
    return None


async def _require_page(request: Request, page_slug: str):
    """
    Check that an active user is logged in and has permission to view the page.

    Security note: authorization is based only on the signed session cookie and
    database state. Display cookies such as user_role/page_permissions are never
    trusted for access control.
    """
    user = await _load_current_user(request)
    if not user:
        return _login_redirect(request)

    if user.role == "admin":
        return None

    if not user.page_permissions:
        # Legacy users with no explicit permission list keep full access.
        return None

    allowed = [p.strip() for p in user.page_permissions.split(",") if p.strip()]
    if page_slug not in allowed:
        return RedirectResponse(url="/?denied=1", status_code=303)

    return None


@router.get("/login")
async def login_page(request: Request):
    user = await _load_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username, User.is_active == True))
    user = result.scalar_one_or_none()

    if user and verify_password(password, user.password_hash):
        response = RedirectResponse(url="/", status_code=303)
        _set_session_cookies(response, user)
        return response

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Неверный логин или пароль",
    })


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    _clear_session_cookies(response)
    return response


@router.get("/settings")
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)

    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()

    from app.models import Setting as SettingModel
    settings_result = await db.execute(select(SettingModel))
    settings_dict = {s.key: s.value for s in settings_result.scalars().all()}
    if "ui_theme" not in settings_dict and "theme" in settings_dict:
        settings_dict["ui_theme"] = settings_dict["theme"]

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "current_user_id": current_user.id,
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
    new_username: str = Form(...),
    current_password: str = Form(""),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)

    username = new_username.strip()
    if not username:
        return RedirectResponse(url="/settings?error=Имя+не+может+быть+пустым", status_code=303)

    if not verify_password(current_password, current_user.password_hash):
        return RedirectResponse(url="/settings?error=Неверный+текущий+пароль", status_code=303)

    existing = await db.execute(select(User).where(User.username == username, User.id != current_user.id))
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/settings?error=Имя+уже+занято", status_code=303)

    current_user.username = username
    await db.commit()

    response = RedirectResponse(url="/settings?success=Имя+изменено", status_code=303)
    _set_session_cookies(response, current_user)
    return response


@router.post("/settings/change-password")
async def change_password(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)

    if not verify_password(current_password, current_user.password_hash):
        return RedirectResponse(url="/settings?error=Неверный+текущий+пароль", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse(url="/settings?error=Пароли+не+совпадают", status_code=303)
    if len(new_password) < 4:
        return RedirectResponse(url="/settings?error=Минимум+4+символа", status_code=303)

    current_user.password_hash = hash_password(new_password)
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
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)
    if current_user.role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    username = username.strip()
    if not username:
        return RedirectResponse(url="/settings?error=Имя+не+может+быть+пустым", status_code=303)
    if len(password) < 4:
        return RedirectResponse(url="/settings?error=Минимум+4+символа", status_code=303)
    if role not in {"admin", "user"}:
        return RedirectResponse(url="/settings?error=Некорректная+роль", status_code=303)

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/settings?error=Имя+уже+занято", status_code=303)

    perms_map = {
        "dashboard": page_dashboard,
        "payments": page_payments,
        "history": page_history,
        "contractors": page_contractors,
        "analytics": page_analytics,
        "settings": page_settings,
    }
    allowed_pages = [slug for slug, val in perms_map.items() if val == "on"]

    new_user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        page_permissions=",".join(allowed_pages),
        is_active=True,
    )
    db.add(new_user)
    await db.commit()

    return RedirectResponse(url="/settings?success=Пользователь+создан", status_code=303)


@router.post("/settings/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)
    if current_user.role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)
    if current_user.id == user_id:
        return RedirectResponse(url="/settings?error=Нельзя+деактивировать+себя", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    if user.role == "admin" and user.is_active:
        admin_count = await db.scalar(select(func.count(User.id)).where(User.role == "admin", User.is_active == True))
        if admin_count <= 1:
            return RedirectResponse(url="/settings?error=Нельзя+деактивировать+последнего+админа", status_code=303)

    user.is_active = not user.is_active
    await db.commit()

    action = "деактивирован" if not user.is_active else "активирован"
    return RedirectResponse(url=f"/settings?success=Пользователь+{action}", status_code=303)


@router.post("/settings/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)
    if current_user.role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)
    if current_user.id == user_id:
        return RedirectResponse(url="/settings?error=Нельзя+удалить+себя", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    if user.role == "admin":
        return RedirectResponse(url="/settings?error=Админа+нельзя+удалить,+можно+только+деактивировать", status_code=303)

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
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)
    if current_user.role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    if role not in {"admin", "user"}:
        return RedirectResponse(url="/settings?error=Некорректная+роль", status_code=303)

    if user.id == current_user.id and current_user.role == "admin" and role != "admin":
        return RedirectResponse(url="/settings?error=Нельзя+снять+админа+с+себя", status_code=303)

    user.role = role
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
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)
    if current_user.role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)

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
    await _upsert("ui_theme", theme if theme in {"dark", "light"} else "dark", "Тема интерфейса")

    await db.commit()
    return RedirectResponse(url="/settings?success=Настройки+сохранены", status_code=303)


@router.post("/settings/theme")
async def change_theme(request: Request, data: dict = Body(...)):
    """AJAX endpoint to save theme preference."""
    theme_val = data.get("theme", "dark")
    if theme_val not in {"dark", "light"}:
        theme_val = "dark"

    async with async_session_factory() as db:
        current_user = await get_current_user(request, db)
        if not current_user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        from app.models import Setting as SettingModel
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
    current_user = await get_current_user(request, db)
    if not current_user:
        return _login_redirect(request)
    if current_user.role != "admin":
        return RedirectResponse(url="/settings?error=Только+для+админа", status_code=303)
    if len(new_password) < 4:
        return RedirectResponse(url="/settings?error=Минимум+4+символа", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    user.password_hash = hash_password(new_password)
    await db.commit()
    return RedirectResponse(url="/settings?success=Пароль+изменён", status_code=303)
