"""
Tests for utility functions.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from app.utils import (
    hash_password,
    verify_password,
    month_name,
    payment_color_class,
    days_until_due,
    is_allowed_file,
    get_upload_path,
    format_currency,
)


class TestPasswordHashing:
    def test_hash_and_verify_correct(self):
        pw = "secret123"
        h = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_verify_wrong_password(self):
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_hash_is_different_each_time(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1)
        assert verify_password("same", h2)


class TestMonthName:
    def test_all_months(self):
        expected = [
            "Январь", "Февраль", "Март", "Апрель",
            "Май", "Июнь", "Июль", "Август",
            "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
        ]
        for i, name in enumerate(expected, 1):
            assert month_name(i) == name

    def test_invalid_month(self):
        assert month_name(0) == ""
        assert month_name(13) == ""


class TestDaysUntilDue:
    def test_future(self):
        d = date.today() + timedelta(days=5)
        assert days_until_due(d) == 5

    def test_today(self):
        assert days_until_due(date.today()) == 0

    def test_past(self):
        d = date.today() - timedelta(days=3)
        assert days_until_due(d) == -3


class TestPaymentColorClass:
    def test_paid(self):
        assert payment_color_class(date.today(), "paid") == "paid"

    def test_overdue_past(self):
        d = date.today() - timedelta(days=5)
        assert payment_color_class(d, "pending") == "overdue"

    def test_overdue_today(self):
        assert payment_color_class(date.today(), "pending") == "overdue"

    def test_soon_3_days(self):
        d = date.today() + timedelta(days=3)
        assert payment_color_class(d, "pending") == "soon"

    def test_pending_10_days(self):
        d = date.today() + timedelta(days=10)
        assert payment_color_class(d, "pending") == "pending"


class TestIsAllowedFile:
    def test_allowed_extensions(self):
        for ext in [".pdf", ".jpg", ".jpeg", ".png"]:
            assert is_allowed_file(f"file{ext}") is True

    def test_mixed_case(self):
        assert is_allowed_file("FILE.PNG") is True
        assert is_allowed_file("file.Pdf") is True

    def test_disallowed(self):
        assert is_allowed_file("file.exe") is False
        assert is_allowed_file("file.docx") is False


class TestGetUploadPath:
    def test_creates_directory(self, tmp_path):
        path = get_upload_path(2025, 6, str(tmp_path))
        assert path == str(tmp_path / "2025" / "06")
        assert (tmp_path / "2025" / "06").is_dir()


class TestFormatCurrency:
    def test_normal(self):
        assert format_currency(Decimal("1250.50")) == "1,250.50 \u20bd"

    def test_zero(self):
        assert format_currency(Decimal("0")) == "0.00 \u20bd"

    def test_none(self):
        assert format_currency(None) == "\u2014"
