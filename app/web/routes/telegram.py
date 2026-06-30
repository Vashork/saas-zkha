"""Admin-only Telegram bot management and message log routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_admin_action
from app.bot.management import (
    DEFAULT_TELEGRAM_BOT_ENABLED,
    TELEGRAM_BOT_ENABLED_KEY,
    is_telegram_setting_enabled,
    normalize_telegram_enabled_value,
)
from app.config import get_settings
from app.database import get_db
from app.models import Setting, TelegramMessageLog, TelegramOutboundMessageLog
from app.web.routes.auth import get_current_user
from app.web.permissions import TELEGRAM_MANAGE, has_action_permission
from app.web.template_engine import templates

router = APIRouter()

TELEGRAM_LOG_MODE_KEY = "telegram_log_mode"
TELEGRAM_LOG_RETENTION_DAYS_KEY = "telegram_log_retention_days"
TELEGRAM_LOG_RETENTION_COUNT_KEY = "telegram_log_retention_count"
TELEGRAM_ALLOWED_USER_IDS_KEY = "telegram_allowed_user_ids"
TELEGRAM_ADMIN_ID_KEY = "telegram_admin_id"
TELEGRAM_LOG_MODES = {"blocked", "allowed", "all"}
DEFAULT_TELEGRAM_LOG_MODE = "all"
DEFAULT_TELEGRAM_LOG_RETENTION_DAYS = "30"
DEFAULT_TELEGRAM_LOG_RETENTION_COUNT = "1000"


async def _upsert_setting(db: AsyncSession, key: str, value: str, description: str) -> None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(Setting(key=key, value=value, description=description))


async def _settings_dict(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(Setting))
    values = {str(row.key): str(row.value) for row in result.scalars().all()}
    values.setdefault(TELEGRAM_LOG_MODE_KEY, DEFAULT_TELEGRAM_LOG_MODE)
    values.setdefault(TELEGRAM_LOG_RETENTION_DAYS_KEY, DEFAULT_TELEGRAM_LOG_RETENTION_DAYS)
    values.setdefault(TELEGRAM_LOG_RETENTION_COUNT_KEY, DEFAULT_TELEGRAM_LOG_RETENTION_COUNT)
    values.setdefault(TELEGRAM_ALLOWED_USER_IDS_KEY, "")
    values.setdefault(TELEGRAM_ADMIN_ID_KEY, "")
    values.setdefault(TELEGRAM_BOT_ENABLED_KEY, DEFAULT_TELEGRAM_BOT_ENABLED)
    return values


def _safe_int(value: str | None, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        parsed = default
    return min(max(parsed, minimum), maximum)


def _parse_int_list(raw: str | None) -> list[int]:
    values: list[int] = []
    seen: set[int] = set()
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            parsed = int(item)
        except ValueError:
            continue
        if parsed not in seen:
            values.append(parsed)
            seen.add(parsed)
    return values


def _normalize_int_csv(raw: str | None) -> str:
    return ",".join(str(v) for v in _parse_int_list(raw))


def _normalize_status(status: str | None) -> str:
    value = (status or "all").strip().lower()
    return value if value in {"all", "blocked", "allowed", "admin"} else "all"


def _row_status(row: TelegramMessageLog) -> str:
    if row.is_admin:
        return "admin"
    return "allowed" if row.is_allowed else "blocked"


def _bot_api_request(token: str, method: str, payload: dict) -> dict:
    if not token:
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN is not configured"}
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "description": str(exc)}
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


def _send_bot_message(token: str, chat_id: int, text: str) -> dict:
    return _bot_api_request(token, "sendMessage", {"chat_id": chat_id, "text": text})


def _edit_bot_message(token: str, chat_id: int, message_id: int, text: str) -> dict:
    return _bot_api_request(token, "editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})


async def _apply_telegram_log_retention(db: AsyncSession, settings: dict[str, str]) -> int:
    """Delete old Telegram log rows according to DB settings; returns deleted count."""
    deleted = 0
    retention_days = _safe_int(
        settings.get(TELEGRAM_LOG_RETENTION_DAYS_KEY),
        int(DEFAULT_TELEGRAM_LOG_RETENTION_DAYS),
        minimum=0,
        maximum=3650,
    )
    retention_count = _safe_int(
        settings.get(TELEGRAM_LOG_RETENTION_COUNT_KEY),
        int(DEFAULT_TELEGRAM_LOG_RETENTION_COUNT),
        minimum=0,
        maximum=100000,
    )

    if retention_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await db.execute(
            delete(TelegramMessageLog).where(TelegramMessageLog.created_at < cutoff)
        )
        deleted += result.rowcount or 0

    if retention_count > 0:
        keep_ids = await db.scalars(
            select(TelegramMessageLog.id)
            .order_by(TelegramMessageLog.id.desc())
            .limit(retention_count)
        )
        ids_to_keep = list(keep_ids)
        if ids_to_keep:
            result = await db.execute(
                delete(TelegramMessageLog).where(TelegramMessageLog.id.not_in(ids_to_keep))
            )
            deleted += result.rowcount or 0

    return deleted


@router.get("/telegram")
async def telegram_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: str = "all",
    user_id: str = "",
    username: str = "",
    chat_id: str = "",
    message_type: str = "",
    q: str = "",
    limit: int = 50,
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    if not has_action_permission(current_user, TELEGRAM_MANAGE):
        return RedirectResponse(url="/?denied=1", status_code=303)

    normalized_status = _normalize_status(status)
    safe_limit = min(max(limit, 10), 200)
    query = select(TelegramMessageLog)

    if normalized_status == "blocked":
        query = query.where(TelegramMessageLog.is_allowed == False, TelegramMessageLog.is_admin == False)
    elif normalized_status == "allowed":
        query = query.where(TelegramMessageLog.is_allowed == True, TelegramMessageLog.is_admin == False)
    elif normalized_status == "admin":
        query = query.where(TelegramMessageLog.is_admin == True)

    if user_id.strip():
        try:
            query = query.where(TelegramMessageLog.telegram_user_id == int(user_id.strip()))
        except ValueError:
            query = query.where(TelegramMessageLog.telegram_user_id == -1)
    if chat_id.strip():
        try:
            query = query.where(TelegramMessageLog.chat_id == int(chat_id.strip()))
        except ValueError:
            query = query.where(TelegramMessageLog.chat_id == -1)
    if username.strip():
        query = query.where(TelegramMessageLog.username.ilike(f"%{username.strip()}%"))
    if message_type.strip():
        query = query.where(TelegramMessageLog.message_type == message_type.strip())
    if q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(or_(TelegramMessageLog.text.ilike(needle), TelegramMessageLog.username.ilike(needle)))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(TelegramMessageLog.id.desc()).limit(safe_limit))
    rows = result.scalars().all()
    outbound_result = await db.execute(
        select(TelegramOutboundMessageLog)
        .order_by(TelegramOutboundMessageLog.id.desc())
        .limit(20)
    )
    outbound_messages = outbound_result.scalars().all()
    settings = await _settings_dict(db)
    app_settings = get_settings()
    db_allowed_ids = _parse_int_list(settings.get(TELEGRAM_ALLOWED_USER_IDS_KEY))
    env_allowed_ids = sorted(app_settings.TELEGRAM_ALLOWED_USER_IDS)
    effective_allowed_ids = sorted(set(db_allowed_ids or env_allowed_ids))
    db_admin_id = settings.get(TELEGRAM_ADMIN_ID_KEY, "").strip()
    effective_admin_id = db_admin_id or app_settings.TELEGRAM_ADMIN_ID

    return templates.TemplateResponse("telegram.html", {
        "request": request,
        "username": current_user.username,
        "user_role": current_user.role,
        "user_theme": settings.get("ui_theme", "dark"),
        "active_page": "telegram",
        "messages": rows,
        "outbound_messages": outbound_messages,
        "message_status": _row_status,
        "total": total or 0,
        "limit": safe_limit,
        "filters": {
            "status": normalized_status,
            "user_id": user_id.strip(),
            "username": username.strip(),
            "chat_id": chat_id.strip(),
            "message_type": message_type.strip(),
            "q": q.strip(),
        },
        "settings": settings,
        "telegram_admin_id": app_settings.TELEGRAM_ADMIN_ID,
        "telegram_allowed_user_ids": sorted(app_settings.TELEGRAM_ALLOWED_USER_IDS),
        "effective_telegram_admin_id": effective_admin_id,
        "effective_telegram_allowed_user_ids": effective_allowed_ids,
        "telegram_bot_enabled": is_telegram_setting_enabled(settings.get(TELEGRAM_BOT_ENABLED_KEY)),
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
    })


@router.post("/telegram/settings")
async def save_telegram_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    telegram_log_mode: str | None = Form(None),
    telegram_log_retention_days: str | None = Form(None),
    telegram_log_retention_count: str | None = Form(None),
    telegram_admin_id: str | None = Form(None),
    telegram_allowed_user_ids: str | None = Form(None),
    telegram_feature_settings_submitted: str | None = Form(None),
    telegram_bot_enabled: str | None = Form(None),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    if not has_action_permission(current_user, TELEGRAM_MANAGE):
        return RedirectResponse(url="/?denied=1", status_code=303)

    current_settings = await _settings_dict(db)
    raw_log_mode = telegram_log_mode if telegram_log_mode is not None else current_settings.get(TELEGRAM_LOG_MODE_KEY)
    raw_retention_days = telegram_log_retention_days if telegram_log_retention_days is not None else current_settings.get(TELEGRAM_LOG_RETENTION_DAYS_KEY)
    raw_retention_count = telegram_log_retention_count if telegram_log_retention_count is not None else current_settings.get(TELEGRAM_LOG_RETENTION_COUNT_KEY)
    raw_admin_id = telegram_admin_id if telegram_admin_id is not None else current_settings.get(TELEGRAM_ADMIN_ID_KEY)
    raw_allowed_ids = telegram_allowed_user_ids if telegram_allowed_user_ids is not None else current_settings.get(TELEGRAM_ALLOWED_USER_IDS_KEY)

    mode = raw_log_mode if raw_log_mode in TELEGRAM_LOG_MODES else DEFAULT_TELEGRAM_LOG_MODE
    retention_days = str(_safe_int(raw_retention_days, 30, minimum=0, maximum=3650))
    retention_count = str(_safe_int(raw_retention_count, 1000, minimum=0, maximum=100000))
    normalized_admin_id = _normalize_int_csv(raw_admin_id)
    normalized_allowed_ids = _normalize_int_csv(raw_allowed_ids)
    bot_enabled = current_settings.get(TELEGRAM_BOT_ENABLED_KEY, DEFAULT_TELEGRAM_BOT_ENABLED)
    if telegram_feature_settings_submitted is not None:
        bot_enabled = normalize_telegram_enabled_value(telegram_bot_enabled, default=False)
    if normalized_admin_id:
        admin_as_list = _parse_int_list(normalized_admin_id)
        allowed = set(_parse_int_list(normalized_allowed_ids))
        allowed.update(admin_as_list)
        normalized_allowed_ids = ",".join(str(v) for v in sorted(allowed))

    await _upsert_setting(db, TELEGRAM_LOG_MODE_KEY, mode, "Режим журнала Telegram: blocked/allowed/all")
    await _upsert_setting(db, TELEGRAM_LOG_RETENTION_DAYS_KEY, retention_days, "Срок хранения Telegram-журнала в днях; 0 отключает")
    await _upsert_setting(db, TELEGRAM_LOG_RETENTION_COUNT_KEY, retention_count, "Максимум записей Telegram-журнала; 0 отключает")
    await _upsert_setting(db, TELEGRAM_ADMIN_ID_KEY, normalized_admin_id, "Telegram admin user id для команд управления")
    await _upsert_setting(db, TELEGRAM_ALLOWED_USER_IDS_KEY, normalized_allowed_ids, "Allowlist Telegram user id через GUI")
    await _upsert_setting(
        db,
        TELEGRAM_BOT_ENABLED_KEY,
        bot_enabled,
        "DB-backed Telegram bot kill switch; 1 включён, 0 выключен",
    )
    deleted = await _apply_telegram_log_retention(db, {
        TELEGRAM_LOG_RETENTION_DAYS_KEY: retention_days,
        TELEGRAM_LOG_RETENTION_COUNT_KEY: retention_count,
    })
    await log_admin_action(
        db,
        actor=current_user,
        action="telegram_settings_update",
        entity_type="settings",
        details={
            "telegram_log_mode": mode,
            "telegram_log_retention_days": retention_days,
            "telegram_log_retention_count": retention_count,
            "telegram_admin_id": normalized_admin_id,
            "telegram_allowed_user_ids": normalized_allowed_ids,
            "telegram_bot_enabled": bot_enabled,
            "deleted_by_retention": deleted,
        },
        request=request,
    )
    await db.commit()
    return RedirectResponse(url="/telegram?success=Настройки+Telegram+сохранены", status_code=303)


@router.post("/telegram/messages/{message_id}/reply")
async def reply_to_telegram_message(
    message_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    reply_text: str = Form(""),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    if not has_action_permission(current_user, TELEGRAM_MANAGE):
        return RedirectResponse(url="/?denied=1", status_code=303)

    text = reply_text.strip()
    if not text:
        return RedirectResponse(url="/telegram?error=Пустой+ответ+Telegram", status_code=303)

    inbound = await db.get(TelegramMessageLog, message_id)
    if not inbound or inbound.chat_id is None:
        return RedirectResponse(url="/telegram?error=Telegram+сообщение+или+chat_id+не+найдены", status_code=303)

    outbound = TelegramOutboundMessageLog(
        inbound_message_id=inbound.id,
        actor_user_id=current_user.id,
        chat_id=inbound.chat_id,
        text=text,
        status="pending",
    )
    db.add(outbound)
    await db.flush()

    result = _send_bot_message(get_settings().TELEGRAM_BOT_TOKEN, inbound.chat_id, text)
    if result.get("ok"):
        outbound.status = "sent"
        outbound.telegram_message_id = result.get("result", {}).get("message_id")
        redirect_url = "/telegram?success=Ответ+Telegram+отправлен"
    else:
        outbound.status = "failed"
        outbound.error_message = str(result.get("description") or result)
        redirect_url = "/telegram?error=Не+удалось+отправить+Telegram+ответ"

    await log_admin_action(
        db,
        actor=current_user,
        action="telegram_reply_send",
        entity_type="telegram_outbound_message",
        entity_id=outbound.id,
        details={"inbound_message_id": inbound.id, "chat_id": inbound.chat_id, "status": outbound.status},
        request=request,
    )
    await db.commit()
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/telegram/outbound/{outbound_id}/edit")
async def edit_telegram_outbound_message(
    outbound_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    edited_text: str = Form(""),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    if not has_action_permission(current_user, TELEGRAM_MANAGE):
        return RedirectResponse(url="/?denied=1", status_code=303)

    text = edited_text.strip()
    if not text:
        return RedirectResponse(url="/telegram?error=Пустой+текст+редактирования", status_code=303)

    outbound = await db.get(TelegramOutboundMessageLog, outbound_id)
    if not outbound or not outbound.telegram_message_id:
        return RedirectResponse(url="/telegram?error=Исходящее+сообщение+не+найдено+или+нет+telegram_message_id", status_code=303)

    result = _edit_bot_message(
        get_settings().TELEGRAM_BOT_TOKEN,
        outbound.chat_id,
        outbound.telegram_message_id,
        text,
    )
    if result.get("ok"):
        outbound.text = text
        outbound.status = "edited"
        outbound.is_edited = True
        outbound.error_message = None
        redirect_url = "/telegram?success=Telegram+сообщение+отредактировано"
    else:
        outbound.status = "failed"
        outbound.error_message = str(result.get("description") or result)
        redirect_url = "/telegram?error=Не+удалось+отредактировать+Telegram+сообщение"

    await log_admin_action(
        db,
        actor=current_user,
        action="telegram_reply_edit",
        entity_type="telegram_outbound_message",
        entity_id=outbound.id,
        details={"chat_id": outbound.chat_id, "telegram_message_id": outbound.telegram_message_id, "status": outbound.status},
        request=request,
    )
    await db.commit()
    return RedirectResponse(url=redirect_url, status_code=303)
