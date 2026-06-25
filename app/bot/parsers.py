"""
Message parser — extracts tags from payment messages like:
  #оплачено #мосэнергосбыт #сумма:3200 #период:2026-06
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass
class ParsedPayment:
    slug: str
    amount: Optional[Decimal] = None
    year: Optional[int] = None
    month: Optional[int] = None


def _parse_amount(text_lower: str) -> Optional[Decimal]:
    amount_match = re.search(r"#сумма[:\s]*([\d_.,]+)", text_lower)
    if not amount_match:
        return None
    try:
        raw = amount_match.group(1).replace("_", "").replace(" ", "")
        if "," in raw and "." in raw:
            raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", ".")
        return Decimal(raw)
    except InvalidOperation:
        return None


def _parse_period(text_lower: str) -> tuple[Optional[int], Optional[int]]:
    """Parse #период:YYYY-MM / #период:YYYY.MM / #период:YYYY/MM."""
    period_match = re.search(r"#период[:\s]*(20\d{2})[-./](0?[1-9]|1[0-2])", text_lower)
    if not period_match:
        return None, None
    return int(period_match.group(1)), int(period_match.group(2))


def parse_payment_message(text: str) -> Optional[ParsedPayment]:
    """
    Parse a message with payment tags.
    Returns ParsedPayment if valid, None otherwise.
    """
    if not text:
        return None

    text_lower = text.lower()

    if "#оплачено" not in text_lower:
        return None

    reserved = {"оплачено", "сумма", "период"}
    all_tags = re.findall(r"#([а-яa-z0-9_-]{2,50})", text_lower)
    slug = None
    for tag in all_tags:
        if tag not in reserved:
            slug = tag
            break

    if not slug:
        return None

    amount = _parse_amount(text_lower)
    year, month = _parse_period(text_lower)

    return ParsedPayment(slug=slug, amount=amount, year=year, month=month)
