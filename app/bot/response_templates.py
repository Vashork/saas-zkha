"""DB-backed Telegram bot response templates."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select

from app.models import Setting

MANAGED_TELEGRAM_RESPONSE_TEMPLATES = (
    "start",
    "help",
    "error_invalid_payment_format",
    "error_invalid_receipt_file",
    "payment_confirmation",
)

_TELEGRAM_TEMPLATE_PREFIX = "telegram_template_"
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")

_HELP_TEMPLATE = (
    "🏠 Добро пожаловать в систему учета ЖКХ!\n\n"
    "💡 Как зафиксировать оплату:\n"
    "Перешлите чек и напишите в сообщении или подписи к чеку:\n"
    "<code>#оплачено #мосэнергосбыт #сумма:3200</code>\n\n"
    "Для старого долга добавьте период:\n"
    "<code>#оплачено #мосэнергосбыт #сумма:1000 #период:2026-06</code>\n\n"
    "Можно просто прислать чек без тегов — я спрошу подрядчика, сумму и период.\n\n"
    "📋 Команды:\n"
    "/balance — остатки по платежам за текущий месяц\n"
    "/contractors — список подрядчиков и их теги\n"
    "/tglog [N] — журнал сообщений боту, только для Telegram-админа\n"
    "/help — это сообщение"
)

DEFAULT_TELEGRAM_RESPONSE_TEMPLATES = {
    "start": _HELP_TEMPLATE,
    "help": _HELP_TEMPLATE,
    "error_invalid_payment_format": (
        "❌ Неверный формат. Используйте: "
        "<code>#оплачено #[slug] #сумма:X</code> или "
        "<code>#оплачено #[slug] #сумма:X #период:2026-06</code>"
    ),
    "error_invalid_receipt_file": "❌ Недопустимый файл чека. Пришлите PDF, JPG или PNG до 10MB.",
    "payment_confirmation": (
        "✅ Оплата <b>{contractor_name}</b> зафиксирована!\n"
        "💰 Сумма: {amount} ₽\n"
        "📅 Период: {period}{receipt_saved_line}"
    ),
}

ALLOWED_TELEGRAM_TEMPLATE_PLACEHOLDERS = {
    "start": frozenset(),
    "help": frozenset(),
    "error_invalid_payment_format": frozenset(),
    "error_invalid_receipt_file": frozenset(),
    "payment_confirmation": frozenset(
        {"contractor_name", "amount", "period", "receipt_saved_line"}
    ),
}


@dataclass(frozen=True)
class TelegramResponseTemplate:
    """One managed Telegram response template definition."""

    name: str
    setting_key: str
    default_text: str
    allowed_placeholders: frozenset[str]


class TelegramTemplateValidationError(ValueError):
    """Raised when a Telegram response template contains unsupported placeholders."""


def telegram_template_setting_key(name: str) -> str:
    """Return the DB setting key for a managed Telegram response template."""
    return f"{_TELEGRAM_TEMPLATE_PREFIX}{name}"


def telegram_response_template_definitions() -> tuple[TelegramResponseTemplate, ...]:
    """Return managed template definitions in stable UI/test order."""
    return tuple(
        TelegramResponseTemplate(
            name=name,
            setting_key=telegram_template_setting_key(name),
            default_text=DEFAULT_TELEGRAM_RESPONSE_TEMPLATES[name],
            allowed_placeholders=ALLOWED_TELEGRAM_TEMPLATE_PLACEHOLDERS[name],
        )
        for name in MANAGED_TELEGRAM_RESPONSE_TEMPLATES
    )


def extract_template_placeholders(template: str) -> set[str]:
    """Extract single-brace placeholder names from a Telegram template."""
    return set(_PLACEHOLDER_RE.findall(template or ""))


def validate_template_placeholders(name: str, template: str) -> None:
    """Reject placeholders that are not allowed for the managed template."""
    if name not in MANAGED_TELEGRAM_RESPONSE_TEMPLATES:
        raise TelegramTemplateValidationError(f"Unknown Telegram response template: {name}")
    unknown = extract_template_placeholders(template) - ALLOWED_TELEGRAM_TEMPLATE_PLACEHOLDERS[name]
    if unknown:
        placeholders = ", ".join(sorted(unknown))
        raise TelegramTemplateValidationError(
            f"Unsupported placeholder(s) for Telegram template {name}: {placeholders}"
        )


def render_template_text(name: str, template: str, context: dict[str, object] | None = None) -> str:
    """Render a validated Telegram template using only allowed placeholders."""
    validate_template_placeholders(name, template)
    values = {key: str(value) for key, value in (context or {}).items()}

    def replace(match: re.Match[str]) -> str:
        placeholder = match.group(1)
        return values.get(placeholder, "")

    return _PLACEHOLDER_RE.sub(replace, template)


async def load_telegram_response_templates(session) -> dict[str, str]:
    """Load Telegram response templates from DB settings, falling back to defaults."""
    defaults = DEFAULT_TELEGRAM_RESPONSE_TEMPLATES.copy()
    key_to_name = {telegram_template_setting_key(name): name for name in defaults}
    result = await session.execute(select(Setting).where(Setting.key.in_(set(key_to_name))))
    templates = defaults.copy()
    for row in result.scalars().all():
        name = key_to_name.get(str(row.key))
        if not name:
            continue
        value = str(row.value)
        try:
            validate_template_placeholders(name, value)
        except TelegramTemplateValidationError:
            continue
        templates[name] = value
    return templates


async def render_telegram_response_template(
    session,
    name: str,
    context: dict[str, object] | None = None,
) -> str:
    """Load and render one managed Telegram response template."""
    templates = await load_telegram_response_templates(session)
    template = templates.get(name, DEFAULT_TELEGRAM_RESPONSE_TEMPLATES[name])
    return render_template_text(name, template, context)
