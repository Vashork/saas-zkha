"""
Shared backup configuration helpers.

Used by both scheduler.py and backups.py to parse and validate
backup_frequency, backup_time, and backup_retention_count settings.
"""


_DEFAULT_RETENTION_COUNT = 10
_DEFAULT_BACKUP_FREQUENCY = "manual"
_DEFAULT_BACKUP_TIME = "03:00"


def parse_retention(value: str | None) -> int:
    """Parse and clamp backup_retention_count to [1, 100]."""
    try:
        count = int(value or _DEFAULT_RETENTION_COUNT)
    except (TypeError, ValueError):
        return _DEFAULT_RETENTION_COUNT
    return max(1, min(count, 100))


def parse_frequency(value: str | None) -> str:
    """Validate backup_frequency against allowed values."""
    if value in {"manual", "daily", "weekly", "monthly"}:
        return value
    return _DEFAULT_BACKUP_FREQUENCY


def parse_time(value: str | None) -> str:
    """Validate and normalize backup_time to HH:MM format."""
    value = value or _DEFAULT_BACKUP_TIME
    try:
        hour, minute = value.split(":")
        h, m = int(hour), int(minute)
    except (ValueError, AttributeError):
        return _DEFAULT_BACKUP_TIME
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return _DEFAULT_BACKUP_TIME
    return f"{h:02d}:{m:02d}"
