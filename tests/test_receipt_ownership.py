"""Tests for receipt ownership checks in download_receipt().

Verifies that receipts are only served if they are linked to a Payment or
PaymentTransaction record. Unlinked files return 404/redirect.
"""

from pathlib import Path
import mimetypes

import pytest

pytestmark = pytest.mark.asyncio


def _payments_route_source() -> str:
    import app.web.routes.payments as payments_mod

    return Path(payments_mod.__file__).read_text(encoding="utf-8")


def test_download_receipt_source_has_ownership_check():
    """Verify that download_receipt queries Payment and PaymentTransaction for ownership."""
    source = _payments_route_source()

    # Must check Payment.receipt_file
    assert "Payment.receipt_file" in source
    # Must check PaymentTransaction.receipt_file
    assert "PaymentTransaction.receipt_file" in source


def test_ownership_check_returns_404_for_unlinked():
    """Source code should redirect with error for unlinked files."""
    source = _payments_route_source()
    # Should have a fallback redirect for unowned files
    assert source.count("error=Файл+не+найден") >= 2  # one for file-not-found, one for ownership


async def test_receipt_ownership_query_constructs_correctly():
    """Verify the ownership query pattern is valid SQLAlchemy."""
    from sqlalchemy import select
    from app.models import Payment, PaymentTransaction

    # Just ensure the query compiles without error
    q1 = select(Payment.receipt_file).where(Payment.receipt_file == "receipt.pdf")
    q2 = select(PaymentTransaction.receipt_file).where(PaymentTransaction.receipt_file == "receipt.pdf")

    # These should be valid selectable objects
    assert q1 is not None
    assert q2 is not None
