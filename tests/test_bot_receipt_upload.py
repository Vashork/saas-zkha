"""Tests for Telegram receipt upload hardening."""

from types import SimpleNamespace

import pytest

from app.bot import handlers
from app.utils import MAX_FILE_SIZE

PDF_MAGIC = b"\x25\x50\x44\x46"
JPG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"
GIF_MAGIC = b"\x47\x49\x46\x38"


class FakeTelegramFile:
    def __init__(self, content: bytes):
        self.content = content

    async def download_to_file(self, filepath: str) -> None:
        with open(filepath, "wb") as f:
            f.write(self.content)


class FakeBot:
    def __init__(self, content: bytes):
        self.content = content
        self.get_file_called = False

    async def get_file(self, file_id: str) -> FakeTelegramFile:
        self.get_file_called = True
        return FakeTelegramFile(self.content)


def _document_message(filename: str, content: bytes, *, file_size: int | None = None):
    return SimpleNamespace(
        document=SimpleNamespace(
            file_id="doc-file-id",
            file_name=filename,
            file_size=len(content) if file_size is None else file_size,
        ),
        photo=None,
        bot=FakeBot(content),
    )


def _photo_message(content: bytes, *, file_size: int | None = None):
    return SimpleNamespace(
        document=None,
        photo=[
            SimpleNamespace(
                file_id="photo-file-id",
                file_size=len(content) if file_size is None else file_size,
            )
        ],
        bot=FakeBot(content),
    )


@pytest.mark.asyncio
async def test_bot_receipt_document_rejects_invalid_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(handlers, "UPLOAD_DIR", str(tmp_path))
    message = _document_message("receipt.gif", GIF_MAGIC + b"content")

    receipt_path = await handlers._download_receipt(message, None, 2026, 6)

    assert receipt_path is None
    assert message.bot.get_file_called is False
    assert not list(tmp_path.rglob("*"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("receipt.pdf", PNG_MAGIC + b"fake pdf"),
        ("receipt.jpg", PDF_MAGIC + b"fake jpg"),
        ("receipt.png", JPG_MAGIC + b"fake png"),
    ],
)
async def test_bot_receipt_document_rejects_spoofed_magic_bytes(
    tmp_path,
    monkeypatch,
    filename,
    content,
):
    monkeypatch.setattr(handlers, "UPLOAD_DIR", str(tmp_path))
    message = _document_message(filename, content)

    receipt_path = await handlers._download_receipt(message, None, 2026, 6)

    assert receipt_path is None
    assert message.bot.get_file_called is True
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


@pytest.mark.asyncio
async def test_bot_receipt_document_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(handlers, "UPLOAD_DIR", str(tmp_path))
    message = _document_message(
        "receipt.pdf",
        PDF_MAGIC + b"content",
        file_size=MAX_FILE_SIZE + 1,
    )

    receipt_path = await handlers._download_receipt(message, None, 2026, 6)

    assert receipt_path is None
    assert message.bot.get_file_called is False
    assert not list(tmp_path.rglob("*"))


@pytest.mark.asyncio
async def test_bot_receipt_photo_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(handlers, "UPLOAD_DIR", str(tmp_path))
    message = _photo_message(
        JPG_MAGIC + b"content",
        file_size=MAX_FILE_SIZE + 1,
    )

    receipt_path = await handlers._download_receipt(message, None, 2026, 6)

    assert receipt_path is None
    assert message.bot.get_file_called is False
    assert not list(tmp_path.rglob("*"))


@pytest.mark.asyncio
async def test_bot_receipt_photo_rejects_spoofed_jpg_magic_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(handlers, "UPLOAD_DIR", str(tmp_path))
    message = _photo_message(PNG_MAGIC + b"fake jpg")

    receipt_path = await handlers._download_receipt(message, None, 2026, 6)

    assert receipt_path is None
    assert message.bot.get_file_called is True
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


@pytest.mark.asyncio
async def test_bot_receipt_document_accepts_valid_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(handlers, "UPLOAD_DIR", str(tmp_path))
    message = _document_message("receipt.pdf", PDF_MAGIC + b"valid pdf")

    receipt_path = await handlers._download_receipt(message, None, 2026, 6)

    assert receipt_path is not None
    assert receipt_path.startswith("2026/06/")
    assert receipt_path.endswith(".pdf")
    saved_files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes().startswith(PDF_MAGIC)
