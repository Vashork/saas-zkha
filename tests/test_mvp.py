from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import (
    RESERVED_SUBDOMAINS,
    Lot,
    PurchaseRequest,
    PurchaseRequestItem,
    Settings,
    Storefront,
    User,
    build_app,
    hash_password,
    validate_subdomain,
)


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


def create_storefront(client: TestClient, subdomain: str = "books") -> int:
    created = client.post("/storefronts", data={"subdomain": subdomain}, follow_redirects=False)
    assert created.status_code == 303
    return int(created.headers["location"].rstrip("/").split("/")[-1])


def create_lot(client: TestClient, storefront_id: int, title: str = "Clean Architecture", quantity: str = "5", published: bool = True) -> int:
    data = {"title": title, "description": "Книга", "price": "1200.50", "quantity": quantity}
    if quantity == "":
        data["infinite_quantity"] = "1"
    if published:
        data["is_published"] = "1"
    response = client.post(f"/storefronts/{storefront_id}/lots", data=data, follow_redirects=False)
    assert response.status_code == 303

    async def fetch_lot_id() -> int:
        async with client.app.state.session_factory() as session:
            return (await session.execute(select(Lot).where(Lot.storefront_id == storefront_id, Lot.title == title))).scalar_one().id

    return asyncio.run(fetch_lot_id())


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
        storefront_id = create_storefront(client, "books")
        create_lot(client, storefront_id, quantity="")
        response = client.get("/", headers={"host": "books.guru.localhost"})
        assert response.status_code == 200
        assert "Clean Architecture" in response.text
        assert "1200.50" in response.text
        assert "Куплю" in response.text


def test_owner_cannot_access_foreign_storefront(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        storefront_id = create_storefront(client, "owner-a")

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
        storefront_id = create_storefront(client, "img")
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
        storefront_id = create_storefront(client, "photo")
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


def test_public_add_to_cart(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        storefront_id = create_storefront(client, "cart")
        lot_id = create_lot(client, storefront_id, title="Book", quantity="5")
        client.post("/logout", follow_redirects=False)
        response = client.post("/s/cart/cart/items", data={"lot_id": lot_id, "quantity": "2"}, follow_redirects=False)
        assert response.status_code == 303
        cart = client.get("/s/cart/cart")
        assert cart.status_code == 200
        assert "Book" in cart.text
        assert 'value="2"' in cart.text


def test_cart_cannot_add_unpublished_lot(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        storefront_id = create_storefront(client, "draft")
        lot_id = create_lot(client, storefront_id, title="Draft", quantity="5", published=False)
        client.post("/logout", follow_redirects=False)
        response = client.post("/s/draft/cart/items", data={"lot_id": lot_id, "quantity": "1"})
        assert response.status_code == 404


def test_cart_cannot_mix_storefronts(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        first = create_storefront(client, "first")
        second = create_storefront(client, "second")
        lot_id = create_lot(client, first, title="First book", quantity="5")
        create_lot(client, second, title="Second book", quantity="5")
        client.post("/logout", follow_redirects=False)
        response = client.post("/s/second/cart/items", data={"lot_id": lot_id, "quantity": "1"})
        assert response.status_code == 404


def test_cart_quantity_validation(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        storefront_id = create_storefront(client, "limited")
        lot_id = create_lot(client, storefront_id, title="Limited", quantity="2")
        client.post("/logout", follow_redirects=False)
        too_many = client.post("/s/limited/cart/items", data={"lot_id": lot_id, "quantity": "3"})
        assert too_many.status_code == 400
        zero = client.post("/s/limited/cart/items", data={"lot_id": lot_id, "quantity": "0"})
        assert zero.status_code == 400


def test_checkout_creates_purchase_request_and_snapshots_lot(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        storefront_id = create_storefront(client, "checkout")
        lot_id = create_lot(client, storefront_id, title="Snapshot book", quantity="5")
        client.post("/logout", follow_redirects=False)
        client.post("/s/checkout/cart/items", data={"lot_id": lot_id, "quantity": "2"}, follow_redirects=False)
        response = client.post(
            "/s/checkout/checkout",
            data={"buyer_name": "Gleb", "buyer_contact": "@gleb", "buyer_email": "g@example.com", "comment": "call me"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        async def fetch_order() -> tuple[PurchaseRequest, PurchaseRequestItem]:
            async with client.app.state.session_factory() as session:
                pr = (await session.execute(select(PurchaseRequest))).scalar_one()
                item = (await session.execute(select(PurchaseRequestItem))).scalar_one()
                return pr, item

        pr, item = asyncio.run(fetch_order())
        assert pr.status == "new"
        assert pr.buyer_contact == "@gleb"
        assert item.lot_title == "Snapshot book"
        assert str(item.price) == "1200.50"
        assert item.quantity == 2


def test_owner_sees_only_own_requests_and_admin_sees_all(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        first_sf = create_storefront(client, "own")
        first_lot = create_lot(client, first_sf, title="Own book")

        async def seed_other() -> None:
            async with client.app.state.session_factory() as session:
                owner2 = User(username="owner2", password_hash=hash_password("owner-pass"), role="owner")
                session.add(owner2)
                await session.flush()
                other_sf = Storefront(owner_id=owner2.id, subdomain="other", title="Other")
                session.add(other_sf)
                await session.flush()
                other_lot = Lot(storefront_id=other_sf.id, title="Other book", description="", price="10.00", quantity=10, is_published=True)
                session.add(other_lot)
                await session.flush()
                req1 = PurchaseRequest(storefront_id=first_sf, buyer_name="A", buyer_contact="a")
                req2 = PurchaseRequest(storefront_id=other_sf.id, buyer_name="B", buyer_contact="b")
                session.add_all([req1, req2])
                await session.flush()
                session.add(PurchaseRequestItem(purchase_request_id=req1.id, lot_id=first_lot, lot_title="Own book", price="1200.50", quantity=1))
                session.add(PurchaseRequestItem(purchase_request_id=req2.id, lot_id=other_lot.id, lot_title="Other book", price="10.00", quantity=1))
                await session.commit()

        asyncio.run(seed_other())
        admin_view = client.get("/requests")
        assert "Own book" in admin_view.text
        assert "Other book" in admin_view.text
        client.post("/logout", follow_redirects=False)
        login(client, "owner2", "owner-pass")
        owner_view = client.get("/requests")
        assert "Other book" in owner_view.text
        assert "Own book" not in owner_view.text


def test_procurement_list_aggregates_quantities(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        storefront_id = create_storefront(client, "proc")
        lot_id = create_lot(client, storefront_id, title="Aggregate", quantity="10")

        async def seed_requests() -> None:
            async with client.app.state.session_factory() as session:
                req1 = PurchaseRequest(storefront_id=storefront_id, buyer_name="A", buyer_contact="a", status="new")
                req2 = PurchaseRequest(storefront_id=storefront_id, buyer_name="B", buyer_contact="b", status="confirmed")
                req3 = PurchaseRequest(storefront_id=storefront_id, buyer_name="C", buyer_contact="c", status="cancelled")
                session.add_all([req1, req2, req3])
                await session.flush()
                session.add_all([
                    PurchaseRequestItem(purchase_request_id=req1.id, lot_id=lot_id, lot_title="Aggregate", price="1200.50", quantity=2),
                    PurchaseRequestItem(purchase_request_id=req2.id, lot_id=lot_id, lot_title="Aggregate", price="1200.50", quantity=3),
                    PurchaseRequestItem(purchase_request_id=req3.id, lot_id=lot_id, lot_title="Aggregate", price="1200.50", quantity=99),
                ])
                await session.commit()

        asyncio.run(seed_requests())
        response = client.get("/procurement")
        assert response.status_code == 200
        assert "Aggregate" in response.text
        assert "Нужно: <strong>5</strong>" in response.text
        assert "1200.50" not in response.text
        assert "6002.50" in response.text


def test_public_cannot_read_request_list(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/requests", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_status_update_requires_owner_or_admin(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client)
        storefront_id = create_storefront(client, "status")
        lot_id = create_lot(client, storefront_id, title="Status book")

        async def seed() -> int:
            async with client.app.state.session_factory() as session:
                session.add(User(username="owner2", password_hash=hash_password("owner-pass"), role="owner"))
                req = PurchaseRequest(storefront_id=storefront_id, buyer_name="A", buyer_contact="a", status="new")
                session.add(req)
                await session.flush()
                session.add(PurchaseRequestItem(purchase_request_id=req.id, lot_id=lot_id, lot_title="Status book", price="1200.50", quantity=1))
                await session.commit()
                return req.id

        request_id = asyncio.run(seed())
        client.post("/logout", follow_redirects=False)
        login(client, "owner2", "owner-pass")
        forbidden = client.post(f"/requests/{request_id}/status", data={"status_value": "confirmed"})
        assert forbidden.status_code == 404
        client.post("/logout", follow_redirects=False)
        login(client)
        ok = client.post(f"/requests/{request_id}/status", data={"status_value": "confirmed"}, follow_redirects=False)
        assert ok.status_code == 303
