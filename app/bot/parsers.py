"""
Message parser — extracts tags from payment messages like:
  #оплачено #мосэнергосбыт #сумма:3200
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass
class ParsedPayment:
    slug: str
    amount: Optional[Decimal] = None


def parse_payment_message(text: str) -> Optional[ParsedPayment]:
    """
    Parse a message with payment tags.
    Returns ParsedPayment if valid, None otherwise.
    """
    if not text:
        return None

    text_lower = text.lower()

    # Check for #оплачено tag
    if "#оплачено" not in text_lower:
        return None

    # Extract contractor slug: first hashtag that is NOT a reserved word
    reserved = {"оплачено", "сумма"}
    all_tags = re.findall(r"#([а-яa-z0-9_-]{2,50})", text_lower)
    slug = None
    for tag in all_tags:
        if tag not in reserved:
            slug = tag
            break

    if not slug:
        return None

    # Extract amount: #сумма:X
    amount_match = re.search(r"#сумма[:\s]*([\d_.,]+)", text_lower)
    amount = None
    if amount_match:
        try:
            raw = amount_match.group(1).replace("_", "").replace(" ", "")
            # Handle both comma and dot as decimal separator
            if "," in raw and "." in raw:
                raw = raw.replace(",", "")
            elif "," in raw:
                raw = raw.replace(",", ".")
            amount = Decimal(raw)
        except InvalidOperation:
            pass

    return ParsedPayment(slug=slug, amount=amount)
