"""
Utility functions: hashing, UUID generation, file validation, date helpers.
"""

import uuid
import os
from datetime import date, datetime
from decimal import Decimal
import bcrypt


def generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def is_allowed_file(filename: str) -> bool:
    """Check if the file extension is allowed."""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


def get_upload_path(year: int, month: int, upload_dir: str) -> str:
    """Get the directory path for uploads of a given year/month."""
    dir_path = os.path.join(upload_dir, str(year), f"{month:02d}")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def month_name(month: int) -> str:
    """Return Russian month name."""
    names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    return names.get(month, "")


def format_currency(amount: Decimal) -> str:
    """Format amount with ₽ symbol."""
    if amount is None:
        return "—"
    return f"{amount:,.2f} ₽"


def days_until_due(due_date: date) -> int:
    """Return number of days until due date (negative if overdue)."""
    return (due_date - date.today()).days


def payment_color_class(due_date: date, status: str) -> str:
    """Return CSS class based on payment urgency."""
    if status == "paid":
        return "paid"
    days = days_until_due(due_date)
    if days < 0:
        return "overdue"
    if days == 0:
        return "overdue"
    if days <= 5:
        return "soon"
    return "pending"
