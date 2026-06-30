"""DB-backed Telegram bot runtime management settings."""

from sqlalchemy import select

from app.models import Setting

TELEGRAM_BOT_ENABLED_KEY = "telegram_bot_enabled"
DEFAULT_TELEGRAM_BOT_ENABLED = "1"

_ENABLED_VALUES = {"1", "true", "yes", "on", "enabled"}
_DISABLED_VALUES = {"0", "false", "no", "off", "disabled"}


def is_telegram_setting_enabled(raw: str | None, *, default: bool = True) -> bool:
    """Parse a stored Telegram feature flag value."""
    value = str(raw if raw is not None else "").strip().lower()
    if value in _ENABLED_VALUES:
        return True
    if value in _DISABLED_VALUES:
        return False
    return default


def normalize_telegram_enabled_value(raw: str | None, *, default: bool = True) -> str:
    """Return a stable string value for storing Telegram feature flags."""
    return "1" if is_telegram_setting_enabled(raw, default=default) else "0"


def is_telegram_bot_enabled(settings: dict[str, str]) -> bool:
    """Return whether the Telegram bot should process inbound messages."""
    return is_telegram_setting_enabled(
        settings.get(TELEGRAM_BOT_ENABLED_KEY),
        default=True,
    )


async def telegram_bot_runtime_settings(session) -> dict[str, str]:
    """Load Telegram runtime feature flags from DB settings."""
    result = await session.execute(
        select(Setting).where(Setting.key.in_({TELEGRAM_BOT_ENABLED_KEY}))
    )
    values = {str(row.key): str(row.value) for row in result.scalars().all()}
    values.setdefault(TELEGRAM_BOT_ENABLED_KEY, DEFAULT_TELEGRAM_BOT_ENABLED)
    return values
