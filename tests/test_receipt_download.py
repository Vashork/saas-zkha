"""Tests for authenticated receipt download route.

Verifies that receipts are served through an authenticated route, blocking
logged-out users, path traversal attempts and unreferenced files.
"""

import pytest
from decimal import Decimal
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.database import Base
from app.models import Contractor, Payment, PaymentTransaction, User
from app.utils import hash_password
from app.web.routes import auth, payments


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _request(path: str, *, method: str = "GET", user: User | None = None) -> Request:
    headers = []
    if user is not None:
        cookie = f"{auth.SESSION_COOKIE}={auth._sign_user_id(user.id)}"
        headers.append((b"cookie", cookie.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers,
            "query_string": b"",
            "client": ("10.0.0.1", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_empty_receive,
    )


@pytest.fixture
async def receipt_db(tmp_path, monkeypatch):
    """Set up a DB with a user, contractor, payment, transaction, and receipt files."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'receipt.db'}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth, "async_session_factory", session_factory)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    uploads_root = tmp_path / "data" / "uploads"
    uploads_dir = uploads_root / "2026" / "06"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / "test-receipt.pdf").write_bytes(b"%PDF-1.4 test content")
    (uploads_dir / "tx-receipt.jpg").write_bytes(b"\xff\xd8\xff\xdb test jpg")
    (uploads_dir / "orphan.pdf").write_bytes(b"%PDF-1.4 orphan content")

    monkeypatch.setattr(payments, "UPLOAD_DIR", str(uploads_root))

    async with session_factory() as session:
        admin = User(
            username="admin",
            password_hash=hash_password("password123"),
            role="admin",
            is_active=True,
        )
        contractor = Contractor(
            id="c-1",
            name="Water",
            slug="water",
            payment_type="fixed",
            fixed_amount=Decimal("100.00"),
            due_day=10,
            is_active=True,
        )
        payment = Payment(
            id="p-1",
            contractor_id="c-1",
            year=2026,
            month=6,
            amount=Decimal("100.00"),
            paid_amount=Decimal("100.00"),
            due_date=date(2026, 6, 10),
            paid_date=date(2026, 6, 5),
            status="paid",
            receipt_file="2026/06/test-receipt.pdf",
        )
        tx = PaymentTransaction(
            id="tx-1",
            payment_id="p-1",
            amount=Decimal("100.00"),
            paid_date=date(2026, 6, 5),
            receipt_file="2026/06/tx-receipt.jpg",
        )
        session.add_all([admin, contractor, payment, tx])
        await session.commit()
        yield session, session_factory, engine, admin, str(uploads_dir)

    await engine.dispose()


@pytest.mark.asyncio
async def test_logged_out_user_cannot_download_receipt(receipt_db):
    """Logged-out user gets redirected to login."""
    session, factory, engine, admin, uploads_dir = receipt_db
    request = _request("/payments/receipts/2026/06/test-receipt.pdf", user=None)

    response = await payments.download_receipt(
        "2026/06/test-receipt.pdf", request, db=session,
    )
    assert response.status_code == 303
    assert "/login" in str(response.headers.get("location", ""))


@pytest.mark.asyncio
async def test_logged_in_user_can_download_payment_receipt_with_pdf_media_type(receipt_db):
    """Authenticated user gets a referenced payment receipt with PDF media type."""
    session, factory, engine, admin, uploads_dir = receipt_db
    request = _request("/payments/receipts/2026/06/test-receipt.pdf", user=admin)

    response = await payments.download_receipt(
        "2026/06/test-receipt.pdf", request, db=session,
    )
    assert response.status_code == 200
    assert response.media_type == "application/pdf"


@pytest.mark.asyncio
async def test_logged_in_user_can_download_transaction_receipt_with_jpeg_media_type(receipt_db):
    """Authenticated user gets a referenced transaction receipt with JPEG media type."""
    session, factory, engine, admin, uploads_dir = receipt_db
    request = _request("/payments/receipts/2026/06/tx-receipt.jpg", user=admin)

    response = await payments.download_receipt(
        "2026/06/tx-receipt.jpg", request, db=session,
    )
    assert response.status_code == 200
    assert response.media_type == "image/jpeg"


@pytest.mark.asyncio
async def test_path_traversal_blocked(receipt_db):
    """Path traversal attempt should be blocked."""
    session, factory, engine, admin, uploads_dir = receipt_db
    request = _request("/payments/receipts/../../../etc/passwd", user=admin)

    response = await payments.download_receipt(
        "../../../etc/passwd", request, db=session,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_existing_but_unreferenced_receipt_is_blocked(receipt_db):
    """A physical file under uploads is denied if no payment/transaction references it."""
    session, factory, engine, admin, uploads_dir = receipt_db
    request = _request("/payments/receipts/2026/06/orphan.pdf", user=admin)

    response = await payments.download_receipt(
        "2026/06/orphan.pdf", request, db=session,
    )
    assert response.status_code == 303
    assert "Файл" in str(response.headers.get("location", "")) or "error" in str(response.headers.get("location", ""))


@pytest.mark.asyncio
async def test_nonexistent_receipt_returns_error(receipt_db):
    """Request for a non-existent receipt returns 303 with error."""
    session, factory, engine, admin, uploads_dir = receipt_db
    request = _request("/payments/receipts/2026/06/does-not-exist.pdf", user=admin)

    response = await payments.download_receipt(
        "2026/06/does-not-exist.pdf", request, db=session,
    )
    assert response.status_code == 303
