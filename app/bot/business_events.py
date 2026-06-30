"""Helpers for linking Telegram messages with business audit events."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any


def telegram_text_hash(text: str | None) -> str:
    """Return a stable privacy-preserving hash for Telegram log/business linkage."""
    normalized = " ".join(str(text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def telegram_message_link_details(message: Any) -> dict[str, Any]:
    """Return safe Telegram message metadata for business audit details."""
    user = getattr(message, "from_user", None)
    chat = getattr(message, "chat", None)
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    return {
        "telegram_chat_id": getattr(chat, "id", None),
        "telegram_message_id": getattr(message, "message_id", None),
        "telegram_text_hash": telegram_text_hash(text),
        "telegram_user_id": getattr(user, "id", None),
        "telegram_username": getattr(user, "username", None),
    }


def telegram_payment_business_details(
    *,
    message: Any,
    payment_id: str,
    contractor_id: str,
    contractor_name: str,
    amount: Decimal,
    year: int,
    month: int,
    receipt_path: str | None,
) -> dict[str, Any]:
    """Return audit-safe details for a payment recorded from Telegram."""
    details = telegram_message_link_details(message)
    details.update({
        "source": "telegram_bot",
        "payment_id": payment_id,
        "contractor_id": contractor_id,
        "contractor_name": contractor_name,
        "amount": str(amount),
        "year": year,
        "month": month,
        "receipt_saved": bool(receipt_path),
    })
    return details
