"""
Tests for bot message parser.
"""

import pytest
from decimal import Decimal
from app.bot.parsers import parse_payment_message


class TestParsePaymentMessage:
    def test_valid_fixed_payment(self):
        msg = "#оплачено #мосэнергосбыт #сумма:3200"
        result = parse_payment_message(msg)
        assert result is not None
        assert result.slug == "мосэнергосбыт"
        assert result.amount == Decimal("3200")

    def test_valid_variable_payment(self):
        msg = "#оплачено #мосгаз #сумма:1250.50"
        result = parse_payment_message(msg)
        assert result.slug == "мосгаз"
        assert result.amount == Decimal("1250.50")

    def test_comma_decimal_separator(self):
        msg = "#оплачено #мосгаз #сумма:1250,50"
        result = parse_payment_message(msg)
        assert result.amount == Decimal("1250.50")

    def test_no_amount(self):
        msg = "#оплачено #мосэнергосбыт"
        result = parse_payment_message(msg)
        assert result.slug == "мосэнергосбыт"
        assert result.amount is None

    def test_case_insensitive_paid_tag(self):
        msg = "#Оплачено #УК_НАШ_ДОМ #сумма:4500"
        result = parse_payment_message(msg)
        assert result.slug == "ук_наш_дом"

    def test_no_paid_tag(self):
        msg = "#мосэнергосбыт #сумма:3200"
        result = parse_payment_message(msg)
        assert result is None

    def test_empty_message(self):
        assert parse_payment_message("") is None
        assert parse_payment_message(None) is None

    def test_no_slug(self):
        msg = "#оплачено #сумма:3200"
        result = parse_payment_message(msg)
        # Both tags are reserved, so no valid slug found
        assert result is None

    def test_underscore_in_slug(self):
        msg = "#оплачено #ук_наш_дом #сумма:4500"
        result = parse_payment_message(msg)
        assert result.slug == "ук_наш_дом"

    def test_invalid_amount_ignored(self):
        msg = "#оплачено #мосэнергосбыт #сумма:abc"
        result = parse_payment_message(msg)
        assert result.slug == "мосэнергосбыт"
        assert result.amount is None
