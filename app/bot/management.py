"""DB-backed Telegram bot runtime management settings."""

from sqlalchemy import select

from app.models import Setting

TELEGRAM_BOT_ENABLED_KEY = "telegram_bot_enabled"
DEFAULT_TELEGRAM_BOT_ENABLED = "1"
MANAGED_TELEGRAM_COMMANDS = ("start", "help", "balance", "contractors", "tglog")

_ENABLED_VALUES = {"1", "true", "yes", "on", "enabled"}
_DISABLED_VALUES = {"0", "false", "no", "off", "disabled"}


def telegram_command_setting_key(command: str) -> str:
    """Return the DB setting key for one managed Telegram slash command."""
    return f"telegram_command_{command}_enabled"


def telegram_command_default_settings() -> dict[str, str]:
    """Return default-on command toggle settings."""
    return {telegram_command_setting_key(command): "1" for command in MANAGED_TELEGRAM_COMMANDS}


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


def is_telegram_command_enabled(settings: dict[str, str], command: str | None) -> bool:
    """Return whether a managed slash command should be processed."""
    if not command:
        return True
    normalized = command.strip().lower().lstrip("/")
    if normalized not in MANAGED_TELEGRAM_COMMANDS:
        return True
    return is_telegram_setting_enabled(
        settings.get(telegram_command_setting_key(normalized)),
        default=True,
    )


async def telegram_bot_runtime_settings(session) -> dict[str, str]:
    """Load Telegram runtime feature flags from DB settings."""
    default_settings = {
        TELEGRAM_BOT_ENABLED_KEY: DEFAULT_TELEGRAM_BOT_ENABLED,
        **telegram_command_default_settings(),
    }
    result = await session.execute(
        select(Setting).where(Setting.key.in_(set(default_settings)))
    )
    values = {str(row.key): str(row.value) for row in result.scalars().all()}
    for key, value in default_settings.items():
        values.setdefault(key, value)
    return values
