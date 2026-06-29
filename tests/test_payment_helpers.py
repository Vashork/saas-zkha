"""
Tests for shared payment helper functions.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from app.web.routes.payment_helpers import (
    _as_decimal,
    _requires_amount,
    _planned_amount,
    _paid_amount,
    _remaining_amount,
    _is_partial_payment,
    _is_open_payment,
    _effective_status,
    _status_label,
    _status_css_class,
    _filter_by_effective_status,
)


# --- _as_decimal ---

def test_as_decimal_none():
    assert _as_decimal(None) == Decimal("0")


def test_as_decimal_decimal():
    assert _as_decimal(Decimal("1500.50")) == Decimal("1500.50")


def test_as_decimal_int():
    assert _as_decimal(3000) == Decimal("3000")


def test_as_decimal_float():
    assert _as_decimal(1500.75) == Decimal("1500.75")


def test_as_decimal_string():
    assert _as_decimal("999.99") == Decimal("999.99")


# --- _requires_amount ---

def test_requires_amount_true():
    payment = MagicMock()
    payment.amount = None
    payment.paid_amount = None
    payment.status = "pending"
    contractor = MagicMock()
    contractor.payment_type = "variable"
    payment.contractor = contractor
    assert _requires_amount(payment) is True


def test_requires_amount_false_fixed():
    payment = MagicMock()
    payment.amount = None
    payment.paid_amount = None
    payment.status = "pending"
    contractor = MagicMock()
    contractor.payment_type = "fixed"
    payment.contractor = contractor
    assert _requires_amount(payment) is False


def test_requires_amount_false_has_amount():
    payment = MagicMock()
    payment.amount = Decimal("1000")
    payment.paid_amount = None
    payment.status = "pending"
    contractor = MagicMock()
    contractor.payment_type = "variable"
    payment.contractor = contractor
    assert _requires_amount(payment) is False


def test_requires_amount_false_paid():
    payment = MagicMock()
    payment.amount = None
    payment.paid_amount = None
    payment.status = "paid"
    contractor = MagicMock()
    contractor.payment_type = "variable"
    payment.contractor = contractor
    assert _requires_amount(payment) is False


def test_requires_amount_no_contractor():
    payment = MagicMock()
    payment.contractor = None
    assert _requires_amount(payment) is False


# --- _planned_amount ---

def test_planned_amount_fixed_contractor():
    payment = MagicMock()
    payment.amount = None
    payment.paid_amount = None
    contractor = MagicMock()
    contractor.payment_type = "fixed"
    contractor.fixed_amount = Decimal("5000")
    payment.contractor = contractor
    assert _planned_amount(payment) == Decimal("5000")


def test_planned_amount_has_payment_amount():
    payment = MagicMock()
    payment.amount = Decimal("3000")
    payment.paid_amount = None
    payment.contractor = None
    assert _planned_amount(payment) == Decimal("3000")


def test_planned_amount_max_of_candidates():
    payment = MagicMock()
    payment.amount = Decimal("4000")
    payment.paid_amount = Decimal("3000")
    contractor = MagicMock()
    contractor.payment_type = "fixed"
    contractor.fixed_amount = Decimal("5000")
    payment.contractor = contractor
    assert _planned_amount(payment) == Decimal("5000")


def test_planned_amount_empty():
    payment = MagicMock()
    payment.amount = None
    payment.paid_amount = None
    payment.contractor = None
    assert _planned_amount(payment) == Decimal("0")


# --- _paid_amount ---

def test_paid_amount_value():
    payment = MagicMock()
    payment.paid_amount = Decimal("2500")
    assert _paid_amount(payment) == Decimal("2500")


def test_paid_amount_none():
    payment = MagicMock()
    payment.paid_amount = None
    assert _paid_amount(payment) == Decimal("0")


# --- _remaining_amount ---

def test_remaining_amount_positive():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("2000")
    payment.contractor = None
    assert _remaining_amount(payment) == Decimal("3000")


def test_remaining_amount_zero_when_paid():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("5000")
    payment.contractor = None
    assert _remaining_amount(payment) == Decimal("0")


def test_remaining_amount_clamped_to_zero():
    payment = MagicMock()
    payment.amount = Decimal("1000")
    payment.paid_amount = Decimal("2000")
    payment.contractor = None
    assert _remaining_amount(payment) == Decimal("0")


# --- _is_partial_payment ---

def test_is_partial_payment_true():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("4500")
    payment.contractor = None
    payment.status = "pending"
    assert _is_partial_payment(payment) is True


def test_is_partial_payment_false_when_not_paid_anything():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("0")
    payment.contractor = None
    payment.status = "pending"
    assert _is_partial_payment(payment) is False


# --- _is_open_payment ---

def test_is_open_with_remaining():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("2000")
    payment.contractor = None
    assert _is_open_payment(payment) is True


def test_is_open_when_fully_paid():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("5000")
    payment.contractor = None
    assert _is_open_payment(payment) is False


# --- _effective_status ---

def test_effective_status_paid():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("5000")
    payment.contractor = None
    payment.status = "pending"
    assert _effective_status(payment) == "paid"


def test_effective_status_overdue_explicit():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("0")
    payment.contractor = None
    payment.status = "overdue"
    payment.due_date = date.today() + timedelta(days=10)
    assert _effective_status(payment) == "overdue"


def test_effective_status_overdue_by_date():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("0")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() - timedelta(days=5)
    assert _effective_status(payment) == "overdue"


def test_effective_status_pending():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("0")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() + timedelta(days=10)
    assert _effective_status(payment) == "pending"


def test_effective_status_partial_before_due_date():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("4500")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() + timedelta(days=10)
    assert _effective_status(payment) == "partial"


def test_effective_status_partial_overdue_after_due_date():
    payment = MagicMock()
    payment.amount = Decimal("5000")
    payment.paid_amount = Decimal("4500")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() - timedelta(days=1)
    assert _effective_status(payment) == "partial_overdue"


# --- _status_label ---

def test_status_label_paid():
    payment = MagicMock()
    payment.amount = Decimal("1000")
    payment.paid_amount = Decimal("1000")
    payment.contractor = None
    assert _status_label(payment) == "оплачено"


def test_status_label_pending():
    payment = MagicMock()
    payment.amount = Decimal("1000")
    payment.paid_amount = Decimal("0")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() + timedelta(days=10)
    assert _status_label(payment) == "к оплате"


def test_status_label_overdue():
    payment = MagicMock()
    payment.amount = Decimal("1000")
    payment.paid_amount = Decimal("0")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() - timedelta(days=1)
    assert _status_label(payment) == "просрочено"


def test_status_label_partial():
    payment = MagicMock()
    payment.amount = Decimal("1000")
    payment.paid_amount = Decimal("500")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() + timedelta(days=1)
    assert _status_label(payment) == "частично оплачено"


def test_status_label_partial_overdue():
    payment = MagicMock()
    payment.amount = Decimal("1000")
    payment.paid_amount = Decimal("500")
    payment.contractor = None
    payment.status = "pending"
    payment.due_date = date.today() - timedelta(days=1)
    assert _status_label(payment) == "частично оплачено, просрочено"


# --- _filter_by_effective_status ---

def test_filter_all():
    payments = [MagicMock(), MagicMock(), MagicMock()]
    assert _filter_by_effective_status(payments, "all") is payments
    assert _filter_by_effective_status(payments, "") is payments


def test_filter_specific():
    p1 = MagicMock()
    p1.amount = Decimal("1000")
    p1.paid_amount = Decimal("1000")
    p1.contractor = None

    p2 = MagicMock()
    p2.amount = Decimal("1000")
    p2.paid_amount = Decimal("0")
    p2.contractor = None
    p2.status = "pending"
    p2.due_date = date.today() + timedelta(days=10)

    payments = [p1, p2]
    result = _filter_by_effective_status(payments, "paid")
    assert len(result) == 1
    assert result[0] is p1


def test_filter_partial():
    partial = MagicMock()
    partial.amount = Decimal("1000")
    partial.paid_amount = Decimal("500")
    partial.contractor = None
    partial.status = "pending"
    partial.due_date = date.today() + timedelta(days=1)

    paid = MagicMock()
    paid.amount = Decimal("1000")
    paid.paid_amount = Decimal("1000")
    paid.contractor = None

    result = _filter_by_effective_status([partial, paid], "partial")
    assert result == [partial]


def test_dashboard_reuses_shared_status_helpers():
    from app.web.routes import dashboard
    from app.web.routes import payment_helpers

    assert dashboard._effective_status is payment_helpers._effective_status
    assert dashboard._status_label is payment_helpers._status_label
    assert dashboard._status_css_class is payment_helpers._status_css_class
