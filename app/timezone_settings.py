"""Shared helpers for user-configurable notification timezones."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_NOTIFICATION_TIMEZONE = "Europe/Moscow"
TIMEZONE_OPTIONS = (
    "Europe/Moscow",
    "Europe/Berlin",
    "UTC",
    "Asia/Yerevan",
    "Asia/Tbilisi",
)


def normalize_timezone(value: str | None, default: str = DEFAULT_NOTIFICATION_TIMEZONE) -> str:
    """Return a valid IANA timezone name, falling back to default when invalid."""
    fallback = (default or DEFAULT_NOTIFICATION_TIMEZONE).strip() or DEFAULT_NOTIFICATION_TIMEZONE
    candidate = (value or fallback).strip()
    try:
        ZoneInfo(candidate)
        return candidate
    except ZoneInfoNotFoundError:
        return fallback
