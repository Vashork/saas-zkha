"""
Shared backup configuration helpers.

Used by both scheduler.py and backups.py to parse and validate
backup_frequency, backup_time, backup_retention_count and remote backup settings.
"""

_DEFAULT_RETENTION_COUNT = 10
_DEFAULT_BACKUP_FREQUENCY = "manual"
_DEFAULT_BACKUP_TIME = "03:00"
_DEFAULT_REMOTE_TYPE = "smb"


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    """Parse common checkbox/string boolean values."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


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


def parse_remote_type(value: str | None) -> str:
    """Validate remote backup target type.

    The first implementation copies to an already-mounted folder. The type still
    records whether the mount represents SMB or SFTP for UI/history clarity.
    """
    if value in {"smb", "sftp"}:
        return value
    return _DEFAULT_REMOTE_TYPE


def normalize_remote_path(value: str | None) -> str:
    """Normalize the configured mounted remote directory path."""
    return (value or "").strip()
