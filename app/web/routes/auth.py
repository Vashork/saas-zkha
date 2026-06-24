"""
Auth routes — login, logout, session management.
"""

from datetime import timedelta
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
