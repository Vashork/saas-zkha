from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import RESERVED_SUBDOMAINS, Settings, Storefront, User, build_app, hash_password, validate_subdomain


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        secret_key="test-secret-that-is-not-production",
        base_domain="guru.localhost",
        allowed_hosts=("testserver", "guru.localhost", "*.guru.localhost", "localhost", "*.localhost"),
        upload_dir=tmp_path / "uploads",
        upload_max_bytes=1024,
        app_env="test",
        auto_create_db=True,
        bootstrap_admin_username="admin",
        bootstrap_admin_password="admin-password",
    )
    return TestClient(build_app(settings))


def login(client: TestClient, username: str = "admin", password: str = "admin-password") -> None:
    response = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert response.status_code == 303


def test_subdomain_validation_accepts_lowercase_dns_label() -> None:
    assert validate_subdomain("Knigi-2026") == "knigi-2026"


def test_subdomain_validation_rejects_reserved_names() -> None:
    for name in RESERVED_SUBDOMAINS:
        try:
            validate_subdomain(name)
        except ValueError:
            pass
        else:
            raise AssertionError(f"reserved name was accepted: {name}")


def test_subdomain_validation_rejects_invalid_labels() -> None:
    for value in ["-bad", "bad-", "two.words", "bad_name", "", "a" * 64]:
        try:
            validate_subdomain(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid label was accepted: {value!r}")


def test_duplicate_subdomain_is_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        first = client.post("/storefronts", data={"subdomain": "knigi"}, follow_redirects=False)
        assert first.status_code == 303
        second = client.post("/storefronts", data={"subdomain": "knigi"})
        assert second.status_code == 409
        assert "Subdomain already exists" in second.text


def test_host_routing_renders_public_storefront(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        created = client.post("/storefronts", data={"subdomain": "knigi"}, follow_redirects=False)
        assert created.status_code == 303
        editor_path = created.headers["location"]
        client.post(editor_path, data={"title": "Книги", "description": "Редкие книги", "is_published": "1"})
        response = client.get("/", headers={"host": "knigi.guru.localhost"})
        assert response.status_code == 200
        assert "Книги" in response.text
        assert "Редкие книги" in response.text


def test_public_page_render_includes_lot(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        created = client.post("/storefronts", data={"subdomain": "books"}, follow_redirects=False)
        storefront_id = int(created.headers["location"].rstrip("/").split("/")[-1])
        lot = client.post(
            f"/storefronts/{storefront_id}/lots",
            data={"title": "Clean Architecture", "description": "Книга", "price": "1200.50", "infinite_quantity": "1", "is_published": "1"},
            follow_redirects=False,
        )
        assert lot.status_code == 303
        response = client.get("/", headers={"host": "books.guru.localhost"})
        assert response.status_code == 200
        assert "Clean Architecture" in response.text
        assert "1200.50" in response.text


def test_owner_cannot_access_foreign_storefront(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        created = client.post("/storefronts", data={"subdomain": "owner-a"}, follow_redirects=False)
        storefront_id = int(created.headers["location"].rstrip("/").split("/")[-1])

        async def add_owner() -> None:
            async with client.app.state.session_factory() as session:
                session.add(User(username="owner2", password_hash=hash_password("owner-pass"), role="owner"))
                await session.commit()

        asyncio.run(add_owner())
        client.post("/logout", follow_redirects=False)
        login(client, "owner2", "owner-pass")
        response = client.get(f"/storefronts/{storefront_id}")
        assert response.status_code == 403


def test_upload_validation_rejects_fake_image_magic_bytes(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        created = client.post("/storefronts", data={"subdomain": "img"}, follow_redirects=False)
        storefront_id = int(created.headers["location"].rstrip("/").split("/")[-1])
        response = client.post(
            f"/storefronts/{storefront_id}/lots",
            data={"title": "Lot", "description": "Bad image", "price": "1", "quantity": "1", "is_published": "1"},
            files={"image": ("bad.png", b"not-a-png", "image/png")},
        )
        assert response.status_code == 400
        assert "Unsupported image content" in response.text


def test_upload_validation_allows_png_and_serves_by_id(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    with make_client(tmp_path) as client:
        login(client)
        created = client.post("/storefronts", data={"subdomain": "photo"}, follow_redirects=False)
        storefront_id = int(created.headers["location"].rstrip("/").split("/")[-1])
        response = client.post(
            f"/storefronts/{storefront_id}/lots",
            data={"title": "Lot", "description": "Good image", "price": "1", "quantity": "1", "is_published": "1"},
            files={"image": ("../ok.png", png, "image/png")},
            follow_redirects=False,
        )
        assert response.status_code == 303

        async def fetch_image_id() -> int:
            async with client.app.state.session_factory() as session:
                sf = (await session.execute(select(Storefront).where(Storefront.subdomain == "photo"))).scalar_one()
                await session.refresh(sf, ["lots"])
                return sf.lots[0].image_id

        image_id = asyncio.run(fetch_image_id())
        image = client.get(f"/uploads/{image_id}")
        assert image.status_code == 200
        assert image.content.startswith(b"\x89PNG")
