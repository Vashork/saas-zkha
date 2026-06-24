"""
Auth routes — login, logout, session management, settings.
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
            max_age=7 * 24 * 60 * 60,  # 7 days
            samesite="lax",
        )
        response.set_cookie(key="username", value=user.username, samesite="lax")
        response.set_cookie(key="user_role", value=user.role, samesite="lax")
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

    result = await db.execute(select(User))
    users = result.scalars().all()

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "username": request.cookies.get("username", "User"),
        "user_role": request.cookies.get("user_role", "user"),
        "users": users,
        "error": None,
        "success": None,
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

    # Require password confirmation
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "username": request.cookies.get("username", "User"),
            "user_role": request.cookies.get("user_role", "user"),
            "users": [],
            "error": "Неверный текущий пароль",
            "success": None,
        })

    # Check uniqueness
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "username": request.cookies.get("username", "User"),
            "user_role": request.cookies.get("user_role", "user"),
            "users": [],
            "error": "Это имя пользователя уже занято",
            "success": None,
        })

    old_username = user.username
    user.username = username

    await db.commit()

    response = RedirectResponse(url="/settings", status_code=303)
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
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "username": request.cookies.get("username", "User"),
            "user_role": request.cookies.get("user_role", "user"),
            "users": [],
            "error": "Неверный текущий пароль",
            "success": None,
        })

    if new_password != confirm_password:
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "username": request.cookies.get("username", "User"),
            "user_role": request.cookies.get("user_role", "user"),
            "users": [],
            "error": "Новый пароль и подтверждение не совпадают",
            "success": None,
        })

    if len(new_password) < 4:
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "username": request.cookies.get("username", "User"),
            "user_role": request.cookies.get("user_role", "user"),
            "users": [],
            "error": "Пароль слишком короткий (минимум 4 символа)",
            "success": None,
        })

    user.password_hash = hash_password(new_password)
    await db.commit()

    response = RedirectResponse(url="/settings", status_code=303)
    # Flash-like via cookie
    response.set_cookie(key="flash_success", value="1", max_age=5, samesite="lax")
    return response
