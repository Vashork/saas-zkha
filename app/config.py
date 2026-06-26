"""
Configuration — loads settings from .env file and database.
"""

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_samesite(name: str, default: str) -> str:
    val = (os.getenv(name) or default).lower()
    if val in ("lax", "strict", "none"):
        return val
    return default


class Settings:
    """Application settings from environment variables.

    All values are read in __init__ so that each new instance
    reflects the current environment (important for testing).
    """

    def __init__(self) -> None:
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/zhkh.db")
        self.UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")
        self.LOG_DIR: str = os.getenv("LOG_DIR", "./logs")

        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_ADMIN_ID: str = os.getenv("TELEGRAM_ADMIN_ID", "")

        self.ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
        self.USER_PASSWORD: str = os.getenv("USER_PASSWORD", "user")

        self.GENERATION_DAY: int = int(os.getenv("GENERATION_DAY", "1"))
        self.GENERATION_TIME: str = os.getenv("GENERATION_TIME", "00:05")
        self.GENERATION_ENABLED: bool = os.getenv("GENERATION_ENABLED", "true").lower() == "true"

        self.NOTIFICATION_TIME: str = os.getenv("NOTIFICATION_TIME", "09:00")
        self.NOTIFICATION_TIMEZONE: str = os.getenv("NOTIFICATION_TIMEZONE", "Europe/Moscow")

        # --- Production hardening ---
        self.APP_ENV: str = os.getenv("APP_ENV", "development")
        self.IS_PRODUCTION: bool = self.APP_ENV in {"production", "prod"}
        self.COOKIE_SECURE: bool = _env_bool("COOKIE_SECURE", self.IS_PRODUCTION)
        self.COOKIE_HTTPONLY: bool = _env_bool("COOKIE_HTTPONLY", True)
        self.COOKIE_SAMESITE: str = _env_samesite("COOKIE_SAMESITE", "lax")
        self.SESSION_COOKIE_MAX_AGE_SECONDS: int = _env_int("SESSION_COOKIE_MAX_AGE_SECONDS", 7 * 24 * 60 * 60)

    def validate_for_startup(self) -> None:
        """Raise RuntimeError if production config is unsafe.

        Never leaks actual secret values in error messages.
        """
        if not self.IS_PRODUCTION:
            return
        if not self.SECRET_KEY or self.SECRET_KEY == "change-me-in-production":
            raise RuntimeError(
                "Production startup blocked: SECRET_KEY must be set to a secure value"
            )
        if self.ADMIN_PASSWORD == "admin":
            raise RuntimeError(
                "Production startup blocked: ADMIN_PASSWORD must be changed from default"
            )
        if self.USER_PASSWORD == "user":
            raise RuntimeError(
                "Production startup blocked: USER_PASSWORD must be changed from default"
            )
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise RuntimeError(
                "Production startup blocked: COOKIE_SAMESITE=none requires COOKIE_SECURE=true"
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_for_startup()
    return settings
