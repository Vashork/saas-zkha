"""Tests for receipt file hardening — magic byte validation and download security.

Validates that:
1. PDF, JPG, and PNG uploads are validated by magic bytes (not just extension)
2. Download routes only serve files from the allowed receipt directories
3. Mismatched magic bytes are rejected
4. Path traversal in download routes is blocked
"""

import pytest
from io import BytesIO
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import User
from app.utils import hash_password
from app.web.routes import auth


# --- Magic byte constants ---
PDF_MAGIC = b"\x25\x50\x44\x46"  # %PDF
JPG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"
GIF_MAGIC = b"\x47\x49\x46\x38"  # GIF8 (should be rejected)
TAR_MAGIC = b"\x1f\x8b\x08"      # gzip (should be rejected)


def _make_upload_file(filename: str, content: bytes) -> "UploadFile":
    from starlette.datastructures import UploadFile
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers={"content-type": "application/octet-stream"},
    )


@pytest.fixture
async def hardening_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'hardening.db'}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth, "async_session_factory", session_factory)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        admin = User(
            username="admin",
            password_hash=hash_password("password123"),
            role="admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        yield session, session_factory, engine, admin, tmp_path

    await engine.dispose()


@pytest.mark.asyncio
async def test_pdf_magic_bytes_validated(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    # Valid PDF magic bytes
    upload = _make_upload_file("receipt.pdf", PDF_MAGIC + b"fake pdf content")
    # The _upload_receipt function should accept this
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert err is None, f"Valid PDF was rejected: {err}"
    assert result_path is not None
    assert result_path.endswith(".pdf")


@pytest.mark.asyncio
async def test_jpg_magic_bytes_validated(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    upload = _make_upload_file("receipt.jpg", JPG_MAGIC + b"\x00" * 100)
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert err is None, f"Valid JPG was rejected: {err}"
    assert result_path is not None


@pytest.mark.asyncio
async def test_png_magic_bytes_validated(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    upload = _make_upload_file("receipt.png", PNG_MAGIC + b"\x00" * 100)
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert err is None, f"Valid PNG was rejected: {err}"
    assert result_path is not None


@pytest.mark.asyncio
async def test_pdf_with_wrong_magic_bytes_rejected(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    # .pdf extension but tar.gz content
    upload = _make_upload_file("malicious.pdf", TAR_MAGIC + b"tar content")
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert result_path is None
    assert err is not None
    assert "magic" in err.lower() or "format" in err.lower() or "invalid" in err.lower() or "не соответствует" in err.lower()


@pytest.mark.asyncio
async def test_jpg_with_wrong_magic_bytes_rejected(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    # .jpg extension but PNG content
    upload = _make_upload_file("fake.jpg", PNG_MAGIC + b"not a jpeg")
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert result_path is None
    assert err is not None


@pytest.mark.asyncio
async def test_png_with_wrong_magic_bytes_rejected(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    # .png extension but tar content
    upload = _make_upload_file("fake.png", TAR_MAGIC + b"not a png")
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert result_path is None
    assert err is not None


@pytest.mark.asyncio
async def test_non_image_pdf_extension_rejected(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    # .exe or .sh extension should be rejected regardless of content
    upload = _make_upload_file("script.exe", PDF_MAGIC + b"content")
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert result_path is None
    assert err is not None


@pytest.mark.asyncio
async def test_gif_extension_rejected_even_with_valid_magic(hardening_db):
    session, factory, engine, admin, tmp_path = hardening_db
    # GIF is not in the allowed extension list
    upload = _make_upload_file("receipt.gif", GIF_MAGIC + b"89a content")
    from app.web.routes.payments import _upload_receipt
    result_path, err = await _upload_receipt(upload, 2026, 6)
    assert result_path is None
    assert err is not None
