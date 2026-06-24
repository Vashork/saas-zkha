"""
Configuration — loads settings from .env file and database.
"""

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


class Settings:
    """Application settings from environment variables."""

    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/zhkh.db")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ADMIN_ID: str = os.getenv("TELEGRAM_ADMIN_ID", "")

    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
    USER_PASSWORD: str = os.getenv("USER_PASSWORD", "user")

    GENERATION_DAY: int = int(os.getenv("GENERATION_DAY", "1"))
    GENERATION_TIME: str = os.getenv("GENERATION_TIME", "00:05")
    GENERATION_ENABLED: bool = os.getenv("GENERATION_ENABLED", "true").lower() == "true"

    NOTIFICATION_TIME: str = os.getenv("NOTIFICATION_TIME", "09:00")
    NOTIFICATION_TIMEZONE: str = os.getenv("NOTIFICATION_TIMEZONE", "Europe/Moscow")


@lru_cache
def get_settings() -> Settings:
    return Settings()
