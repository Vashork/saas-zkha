"""
Auth routes — login, logout, session management, user management.
"""

import base64
import hashlib
import hmac
import ipaddress
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Request, Form, Depends, Body
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_admin_action
from app.config import get_settings
from app.database import get_db, async_session_factory
from app.models import User
from app.utils import verify_password, hash_password
from app.rate_limiter import _is_rate_limited, _record_attempt
from app.web.template_engine import templates
from app.web.permissions import SYSTEM_SETTINGS_MANAGE, USERS_MANAGE, has_action_permission

logger = logging.getLogger("zhkh.auth")

router = APIRouter()

SESSION_COOKIE = "session"
LEGACY_COOKIES = ("user_id", "username", "user_role", "page_permissions")
SESSION_BOOT_ID = secrets.token_urlsafe(32)

ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"
ROLE_LEGACY_USER = "user"
ALLOWED_ROLES = {ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER}
ROLE_OPTIONS = [
    (ROLE_ADMIN, "👑 Системный админ"),
    (ROLE_OPERATOR, "🛠️ Оператор ЛК"),
    (ROLE_VIEWER, "👁️ Наблюдатель"),
]
ROLE_LABELS = {
    ROLE_ADMIN: "👑 Системный админ",
    ROLE_OPERATOR: "🛠️ Оператор ЛК",
    ROLE_VIEWER: "👁️ Наблюдатель",
    ROLE_LEGACY_USER: "👁️ Наблюдатель (legacy user)",
}

PAGES = [
    ("dashboard", "📊 Дашборд"),
    ("payments", "💳 Платежи"),
    ("history", "📜 История"),
    ("contractors", "🏢 Подрядчики"),
    ("analytics", "📈 Аналитика"),
    ("settings", "⚙️ Настройки"),
]


def _normalize_role(role: str | None) -> str | None:
    """Return a supported role value, mapping legacy 'user' to viewer."""
    value = (role or "").strip().lower()
    if value == ROLE_LEGACY_USER:
        return ROLE_VIEWER
    if value in ALLOWED_ROLES:
        return value
    return None


def _is_admin_role(role: str | None) -> bool:
    return role == ROLE_ADMIN


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
    settings = get_settings()
    max_age = settings.SESSION_COOKIE_MAX_AGE_SECONDS
    response.set_cookie(
        key=SESSION_COOKIE,
        value=_sign_user_id(user.id),
        httponly=settings.COOKIE_HTTPONLY,
        max_age=max_age,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
    )
    # Display-only legacy cookies. Authorization never trusts them.
    for name, value in (
        ("user_id", str(user.id)),
        ("username", user.username),
        ("user_role", user.role),
        ("page_permissions", getattr(user, "page_permissions", None) or ""),
    ):
        response.set_cookie(
            key=name,
            value=value,
            httponly=True,
            max_age=max_age,
            samesite=settings.COOKIE_SAMESITE,
            secure=settings.COOKIE_SECURE,
        )


def _clear_session_cookies(response: RedirectResponse) -> None:
    settings = get_settings()
    kwargs = {"secure": settings.COOKIE_SECURE, "samesite": settings.COOKIE_SAMESITE}
    response.delete_cookie(SESSION_COOKIE, **kwargs)
    for cookie_name in LEGACY_COOKIES:
        response.delete_cookie(cookie_name, **kwargs)


def _is_trusted_proxy_host(host: str | None) -> bool:
    """Return True for local/private proxy addresses that may set forwarded IP headers."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host in {"localhost", "nginx", "zhkh-nginx"}
    return ip.is_loopback or ip.is_private


def _first_forwarded_for(value: str | None) -> str | None:
    """Return first valid client IP from X-Forwarded-For."""
    if not value:
        return None
    first = value.split(",", 1)[0].strip()
    if not first:
        return None
    try:
        ipaddress.ip_address(first)
    except ValueError:
        return None
    return first


def _login_rate_limit_key(request: Request) -> str:
    """Choose a per-client rate-limit key, respecting nginx proxy headers."""
    peer_host = request.client.host if request.client else None
    if _is_trusted_proxy_host(peer_host):
        forwarded_for = _first_forwarded_for(request.headers.get("x-forwarded-for"))
        if forwarded_for:
            return forwarded_for
        real_ip = _first_forwarded_for(request.headers.get("x-real-ip"))
        if real_ip:
            return real_ip
    return peer_host or "unknown"


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
    if not _is_admin_role(user.role):
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

    if _is_admin_role(user.role):
        return None

    if user.page_permissions is None:
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
    # Rate limit by real client IP when running behind nginx/reverse proxy.
    client_ip = _login_rate_limit_key(request)
    if _is_rate_limited(client_ip):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Слишком много попыток. Попробуйте через минуту.",
        })

    result = await db.execute(select(User).where(User.username == username, User.is_active == True))
    user = result.scalar_one_or_none()

    if user and verify_password(password, user.password_hash):
        _record_attempt(client_ip)  # Record successful attempt too
        response = RedirectResponse(url="/", status_code=303)
        _set_session_cookies(response, user)
        return response

    _record_attempt(client_ip)
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
        "role_options": ROLE_OPTIONS,
        "role_labels": ROLE_LABELS,
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
    if len(new_password) < 8:
        return RedirectResponse(url="/settings?error=Минимум+8+символов", status_code=303)

    current_user.password_hash = hash_password(new_password)
    await db.commit()
    return RedirectResponse(url="/settings?success=Пароль+изменён", status_code=303)


@router.post("/settings/users/create")
async def create_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form(ROLE_VIEWER),
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
    if not has_action_permission(current_user, USERS_MANAGE):
        return RedirectResponse(url="/settings?error=Недостаточно+прав", status_code=303)

    username = username.strip()
    if not username:
        return RedirectResponse(url="/settings?error=Имя+не+может+быть+пустым", status_code=303)
    if len(password) < 8:
        return RedirectResponse(url="/settings?error=Минимум+8+символов", status_code=303)
    normalized_role = _normalize_role(role)
    if normalized_role is None:
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
        role=normalized_role,
        page_permissions=",".join(allowed_pages),
        is_active=True,
    )
    db.add(new_user)
    await db.flush()
    await log_admin_action(
        db,
        actor=current_user,
        action="user_create",
        entity_type="user",
        entity_id=new_user.id,
        details={"username": username, "role": normalized_role, "page_permissions": allowed_pages},
        request=request,
    )
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
    if not has_action_permission(current_user, USERS_MANAGE):
        return RedirectResponse(url="/settings?error=Недостаточно+прав", status_code=303)
    if current_user.id == user_id:
        return RedirectResponse(url="/settings?error=Нельзя+деактивировать+себя", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    if _is_admin_role(user.role) and user.is_active:
        admin_count = await db.scalar(select(func.count(User.id)).where(User.role == ROLE_ADMIN, User.is_active == True))
        if admin_count <= 1:
            return RedirectResponse(url="/settings?error=Нельзя+деактивировать+последнего+админа", status_code=303)

    old_active = bool(user.is_active)
    user.is_active = not user.is_active
    await log_admin_action(
        db,
        actor=current_user,
        action="user_toggle_active",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username, "old_active": old_active, "new_active": bool(user.is_active)},
        request=request,
    )
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
    if not has_action_permission(current_user, USERS_MANAGE):
        return RedirectResponse(url="/settings?error=Недостаточно+прав", status_code=303)
    if current_user.id == user_id:
        return RedirectResponse(url="/settings?error=Нельзя+удалить+себя", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    if _is_admin_role(user.role):
        return RedirectResponse(url="/settings?error=Админа+нельзя+удалить,+можно+только+деактивировать", status_code=303)

    await log_admin_action(
        db,
        actor=current_user,
        action="user_delete",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username, "role": user.role},
        request=request,
    )
    await db.delete(user)
    await db.commit()
    return RedirectResponse(url="/settings?success=Пользователь+удалён", status_code=303)


@router.post("/settings/users/{user_id}/update")
async def update_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    role: str = Form(ROLE_VIEWER),
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
    if not has_action_permission(current_user, USERS_MANAGE):
        return RedirectResponse(url="/settings?error=Недостаточно+прав", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    normalized_role = _normalize_role(role)
    if normalized_role is None:
        return RedirectResponse(url="/settings?error=Некорректная+роль", status_code=303)

    if user.id == current_user.id and _is_admin_role(current_user.role) and normalized_role != ROLE_ADMIN:
        return RedirectResponse(url="/settings?error=Нельзя+снять+админа+с+себя", status_code=303)

    old_role = user.role
    old_permissions = user.page_permissions
    user.role = normalized_role
    perms_map = {
        "dashboard": page_dashboard,
        "payments": page_payments,
        "history": page_history,
        "contractors": page_contractors,
        "analytics": page_analytics,
        "settings": page_settings,
    }
    allowed_pages = [slug for slug, val in perms_map.items() if val == "on"]
    user.page_permissions = ",".join(allowed_pages)

    await log_admin_action(
        db,
        actor=current_user,
        action="user_update",
        entity_type="user",
        entity_id=user.id,
        details={
            "username": user.username,
            "old_role": old_role,
            "new_role": normalized_role,
            "old_page_permissions": old_permissions,
            "new_page_permissions": user.page_permissions,
        },
        request=request,
    )
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
    if not has_action_permission(current_user, SYSTEM_SETTINGS_MANAGE):
        return RedirectResponse(url="/settings?error=Недостаточно+прав", status_code=303)

    from app.models import Setting as SettingModel

    async def _upsert(key: str, value: str, description: str):
        result = await db.execute(select(SettingModel).where(SettingModel.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            db.add(SettingModel(key=key, value=value, description=description))

    normalized_theme = theme if theme in {"dark", "light"} else "dark"
    normalized_notifications = "on" if notifications_enabled == "on" else "off"
    await _upsert("default_due_day", default_due_day, "День платежа по умолчанию (1-28)")
    await _upsert("notifications_enabled", normalized_notifications, "Включить уведомления")
    await _upsert("ui_theme", normalized_theme, "Тема интерфейса")

    await log_admin_action(
        db,
        actor=current_user,
        action="app_settings_update",
        entity_type="settings",
        details={
            "default_due_day": default_due_day,
            "notifications_enabled": normalized_notifications,
            "ui_theme": normalized_theme,
        },
        request=request,
    )
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
    if not has_action_permission(current_user, USERS_MANAGE):
        return RedirectResponse(url="/settings?error=Недостаточно+прав", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse(url="/settings?error=Минимум+8+символов", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/settings?error=Пользователь+не+найден", status_code=303)

    user.password_hash = hash_password(new_password)
    await log_admin_action(
        db,
        actor=current_user,
        action="user_password_reset",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username},
        request=request,
    )
    await db.commit()
    return RedirectResponse(url="/settings?success=Пароль+изменён", status_code=303)
