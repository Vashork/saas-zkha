from __future__ import annotations

import hashlib
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePath
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

RESERVED_SUBDOMAINS = {"www", "admin", "api", "static", "root", "mail", "ftp", "localhost"}
SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_EXT_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
REQUEST_STATUSES = {"new", "confirmed", "cancelled", "procurement", "fulfilled"}
PROCUREMENT_STATUSES = {"new", "confirmed"}


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="owner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    storefronts: Mapped[list["Storefront"]] = relationship(back_populates="owner")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Storefront(Base):
    __tablename__ = "storefronts"
    __table_args__ = (UniqueConstraint("subdomain", name="uq_storefronts_subdomain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    subdomain: Mapped[str] = mapped_column(String(63), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), default="Новая витрина", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    banner_image_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_images.id", ondelete="SET NULL"), nullable=True)
    seo_title: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    seo_description: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    owner: Mapped[User] = relationship(back_populates="storefronts")
    lots: Mapped[list["Lot"]] = relationship(back_populates="storefront", cascade="all, delete-orphan", order_by="Lot.id")
    banner_image: Mapped["UploadedImage | None"] = relationship(foreign_keys=[banner_image_id])
    purchase_requests: Mapped[list["PurchaseRequest"]] = relationship(back_populates="storefront")


class UploadedImage(Base):
    __tablename__ = "uploaded_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    storefront_id: Mapped[int | None] = mapped_column(ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storefront_id: Mapped[int] = mapped_column(ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=False, index=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_images.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    storefront: Mapped[Storefront] = relationship(back_populates="lots")
    image: Mapped[UploadedImage | None] = relationship()


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (UniqueConstraint("storefront_id", "token_hash", name="uq_carts_storefront_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storefront_id: Mapped[int] = mapped_column(ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    storefront: Mapped[Storefront] = relationship()
    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "lot_id", name="uq_cart_items_cart_lot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped[Cart] = relationship(back_populates="items")
    lot: Mapped[Lot] = relationship()


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storefront_id: Mapped[int] = mapped_column(ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    buyer_contact: Mapped[str] = mapped_column(String(160), nullable=False)
    buyer_email: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    storefront: Mapped[Storefront] = relationship(back_populates="purchase_requests")
    items: Mapped[list["PurchaseRequestItem"]] = relationship(back_populates="purchase_request", cascade="all, delete-orphan")


class PurchaseRequestItem(Base):
    __tablename__ = "purchase_request_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_request_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id", ondelete="SET NULL"), nullable=True, index=True)
    lot_title: Mapped[str] = mapped_column(String(160), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    purchase_request: Mapped[PurchaseRequest] = relationship(back_populates="items")
    lot: Mapped[Lot | None] = relationship()


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    base_domain: str
    allowed_hosts: tuple[str, ...]
    upload_dir: Path
    upload_max_bytes: int
    app_env: str
    auto_create_db: bool
    bootstrap_admin_username: str
    bootstrap_admin_password: str

    @classmethod
    def from_env(cls) -> "Settings":
        app_env = os.getenv("APP_ENV", "development")
        secret_key = os.getenv("SECRET_KEY", "")
        if app_env == "production" and (not secret_key or secret_key in {"dev-secret", "change-me", "secret"}):
            raise RuntimeError("Unsafe SECRET_KEY is not allowed in production")
        if not secret_key:
            secret_key = "dev-secret"
        base_domain = normalize_domain(os.getenv("BASE_DOMAIN", "guru.localhost"))
        allowed_hosts_env = os.getenv("ALLOWED_HOSTS", f"{base_domain},*.{base_domain},localhost,*.localhost,127.0.0.1,testserver")
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/storefront.db"),
            secret_key=secret_key,
            base_domain=base_domain,
            allowed_hosts=tuple(h.strip() for h in allowed_hosts_env.split(",") if h.strip()),
            upload_dir=Path(os.getenv("UPLOAD_DIR", "./data/uploads")).resolve(),
            upload_max_bytes=int(os.getenv("UPLOAD_MAX_BYTES", str(5 * 1024 * 1024))),
            app_env=app_env,
            auto_create_db=os.getenv("AUTO_CREATE_DB", "false").lower() in {"1", "true", "yes"},
            bootstrap_admin_username=os.getenv("ADMIN_USERNAME", "admin"),
            bootstrap_admin_password=os.getenv("ADMIN_PASSWORD", "admin"),
        )


def normalize_domain(value: str) -> str:
    domain = value.strip().strip(".").lower()
    if not domain or "/" in domain or " " in domain:
        raise ValueError("Invalid base domain")
    return domain


def normalize_host(host_header: str | None) -> str:
    if not host_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Host header")
    host = host_header.split(",", 1)[0].strip().lower().rstrip(".")
    if host.startswith("[") and "]" in host:
        return host.split("]", 1)[0] + "]"
    return host.rsplit(":", 1)[0]


def validate_subdomain(raw: str) -> str:
    subdomain = raw.strip().lower()
    if subdomain in RESERVED_SUBDOMAINS:
        raise ValueError("This subdomain is reserved")
    if not SUBDOMAIN_RE.fullmatch(subdomain):
        raise ValueError("Subdomain must be a DNS label: lowercase letters, digits and hyphen, 1-63 chars")
    return subdomain


def extract_subdomain_from_host(host_header: str | None, base_domain: str) -> str | None:
    host = normalize_host(host_header)
    base = normalize_domain(base_domain)
    if host == base:
        return None
    suffix = f".{base}"
    if not host.endswith(suffix):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown host")
    label = host[: -len(suffix)]
    if "." in label:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nested subdomains are not supported")
    try:
        return validate_subdomain(label)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 210_000)
    return f"pbkdf2_sha256$210000${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations_raw)).hex()
        return secrets.compare_digest(candidate, digest)
    except Exception:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def parse_price(value: str) -> Decimal:
    try:
        price = Decimal(value.replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid price") from exc
    if price < 0:
        raise HTTPException(status_code=400, detail="Price must be non-negative")
    return price


def parse_quantity(is_infinite: str | None, quantity_raw: str | None) -> int | None:
    if is_infinite:
        return None
    if quantity_raw is None or quantity_raw.strip() == "":
        raise HTTPException(status_code=400, detail="Quantity is required unless infinite is selected")
    try:
        quantity = int(quantity_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid quantity") from exc
    if quantity < 0:
        raise HTTPException(status_code=400, detail="Quantity must be non-negative")
    return quantity


def parse_order_quantity(quantity_raw: str | int | None) -> int:
    try:
        quantity = int(str(quantity_raw or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cart quantity") from exc
    if quantity < 1:
        raise HTTPException(status_code=400, detail="Cart quantity must be at least 1")
    return quantity


def clean_form_text(value: str, max_length: int, *, required: bool = False) -> str:
    cleaned = " ".join(value.strip().split())
    if required and not cleaned:
        raise HTTPException(status_code=400, detail="Required field is empty")
    return cleaned[:max_length]


def detect_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def safe_original_filename(filename: str | None) -> str:
    if not filename:
        return "upload"
    name = PurePath(filename).name.replace("\x00", "")
    return name[:255] or "upload"


def ensure_child_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if root_resolved != candidate and root_resolved not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    return candidate


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    app = FastAPI(title="Storefront Builder MVP")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=settings.app_env == "production")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    async def get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User | None:
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        user = await session.get(User, int(user_id))
        if not user or not user.is_active:
            request.session.clear()
            return None
        return user

    async def require_user(user: User | None = Depends(current_user)) -> User:
        if not user:
            raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
        return user

    async def require_admin(user: User = Depends(require_user)) -> User:
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
        return user

    async def get_storefront_for_owner(storefront_id: int, user: User, session: AsyncSession) -> Storefront:
        query = select(Storefront).where(Storefront.id == storefront_id).options(selectinload(Storefront.lots).selectinload(Lot.image), selectinload(Storefront.banner_image))
        storefront = (await session.execute(query)).scalar_one_or_none()
        if not storefront:
            raise HTTPException(status_code=404, detail="Storefront not found")
        if user.role != "admin" and storefront.owner_id != user.id:
            raise HTTPException(status_code=403, detail="Not your storefront")
        return storefront

    async def get_base_domain(session: AsyncSession) -> str:
        setting = await session.get(AppSetting, "base_domain")
        return normalize_domain(setting.value if setting else settings.base_domain)

    async def save_image(upload: UploadFile | None, owner: User, session: AsyncSession, storefront_id: int | None = None) -> UploadedImage | None:
        if not upload or not upload.filename:
            return None
        original = safe_original_filename(upload.filename)
        ext = Path(original).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported image extension")
        data = await upload.read(settings.upload_max_bytes + 1)
        if len(data) > settings.upload_max_bytes:
            raise HTTPException(status_code=400, detail="Image is too large")
        mime = detect_image_mime(data)
        if mime is None:
            raise HTTPException(status_code=400, detail="Unsupported image content")
        stored_relative = f"images/{uuid.uuid4().hex}{IMAGE_EXT_BY_MIME[mime]}"
        target = ensure_child_path(settings.upload_dir, stored_relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        image = UploadedImage(
            owner_id=owner.id,
            storefront_id=storefront_id,
            original_filename=original,
            stored_path=stored_relative,
            content_type=mime,
            size_bytes=len(data),
        )
        session.add(image)
        await session.flush()
        return image

    async def get_storefront_by_subdomain(subdomain: str, session: AsyncSession) -> Storefront:
        try:
            normalized = validate_subdomain(subdomain)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        query = select(Storefront).where(Storefront.subdomain == normalized).options(selectinload(Storefront.banner_image))
        storefront = (await session.execute(query)).scalar_one_or_none()
        if not storefront:
            raise HTTPException(status_code=404, detail="Storefront not found")
        return storefront

    async def get_storefront_from_host(request: Request, session: AsyncSession) -> Storefront:
        base_domain = await get_base_domain(session)
        subdomain = extract_subdomain_from_host(request.headers.get("host"), base_domain)
        if not subdomain:
            raise HTTPException(status_code=404, detail="Storefront host required")
        return await get_storefront_by_subdomain(subdomain, session)

    async def load_cart(request: Request, storefront: Storefront, session: AsyncSession) -> Cart | None:
        token_by_storefront = request.session.get("cart_tokens", {})
        token = token_by_storefront.get(str(storefront.id)) if isinstance(token_by_storefront, dict) else None
        if not token:
            return None
        cart = (
            await session.execute(
                select(Cart)
                .where(Cart.storefront_id == storefront.id, Cart.token_hash == token_hash(token))
                .options(selectinload(Cart.items).selectinload(CartItem.lot).selectinload(Lot.image))
            )
        ).scalar_one_or_none()
        if cart and cart.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            await session.delete(cart)
            await session.commit()
            return None
        return cart

    async def get_or_create_cart(request: Request, storefront: Storefront, session: AsyncSession) -> Cart:
        cart = await load_cart(request, storefront, session)
        if cart:
            return cart
        token = secrets.token_urlsafe(32)
        token_by_storefront = request.session.get("cart_tokens", {})
        if not isinstance(token_by_storefront, dict):
            token_by_storefront = {}
        token_by_storefront[str(storefront.id)] = token
        request.session["cart_tokens"] = token_by_storefront
        cart = Cart(
            storefront_id=storefront.id,
            token_hash=token_hash(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(cart)
        await session.flush()
        return cart

    def validate_lot_for_cart(storefront: Storefront, lot: Lot | None, quantity: int) -> Lot:
        if not lot or lot.storefront_id != storefront.id or not lot.is_published:
            raise HTTPException(status_code=404, detail="Published lot not found for this storefront")
        if lot.quantity is not None and quantity > lot.quantity:
            raise HTTPException(status_code=400, detail="Requested quantity exceeds available quantity")
        return lot

    async def render_public_storefront(request: Request, storefront: Storefront, session: AsyncSession, public_prefix: str) -> HTMLResponse:
        if not storefront.is_published:
            raise HTTPException(status_code=404, detail="Storefront is not published")
        lots = (
            await session.execute(
                select(Lot).where(Lot.storefront_id == storefront.id, Lot.is_published.is_(True)).options(selectinload(Lot.image)).order_by(Lot.id)
            )
        ).scalars().all()
        cart = await load_cart(request, storefront, session)
        cart_count = sum(item.quantity for item in cart.items) if cart else 0
        return templates.TemplateResponse(
            request,
            "public_storefront.html",
            {"storefront": storefront, "lots": lots, "base_domain": await get_base_domain(session), "public_prefix": public_prefix, "cart_count": cart_count},
        )

    async def render_cart(request: Request, storefront: Storefront, session: AsyncSession, public_prefix: str, error: str | None = None) -> HTMLResponse:
        cart = await load_cart(request, storefront, session)
        items = cart.items if cart else []
        return templates.TemplateResponse(request, "cart.html", {"storefront": storefront, "items": items, "public_prefix": public_prefix, "error": error})

    async def add_cart_item(request: Request, storefront: Storefront, lot_id: int, quantity_raw: str, session: AsyncSession, public_prefix: str) -> RedirectResponse:
        quantity = parse_order_quantity(quantity_raw)
        lot = validate_lot_for_cart(storefront, await session.get(Lot, lot_id), quantity)
        cart = await get_or_create_cart(request, storefront, session)
        existing = (await session.execute(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.lot_id == lot.id))).scalar_one_or_none()
        new_quantity = quantity + (existing.quantity if existing else 0)
        validate_lot_for_cart(storefront, lot, new_quantity)
        if existing:
            existing.quantity = new_quantity
        else:
            session.add(CartItem(cart_id=cart.id, lot_id=lot.id, quantity=quantity))
        cart.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return RedirectResponse(f"{public_prefix}/cart", status_code=303)

    async def update_cart_item(request: Request, storefront: Storefront, lot_id: int, quantity_raw: str, action: str, session: AsyncSession, public_prefix: str) -> RedirectResponse:
        cart = await load_cart(request, storefront, session)
        if not cart:
            return RedirectResponse(f"{public_prefix}/cart", status_code=303)
        item = (await session.execute(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.lot_id == lot_id))).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Cart item not found")
        if action == "delete":
            await session.delete(item)
        else:
            quantity = parse_order_quantity(quantity_raw)
            lot = validate_lot_for_cart(storefront, await session.get(Lot, lot_id), quantity)
            item.quantity = quantity
            item.lot = lot
        cart.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return RedirectResponse(f"{public_prefix}/cart", status_code=303)

    async def create_purchase_request_from_cart(
        request: Request,
        storefront: Storefront,
        buyer_name: str,
        buyer_contact: str,
        buyer_email: str,
        comment: str,
        session: AsyncSession,
        public_prefix: str,
    ) -> RedirectResponse | HTMLResponse:
        cart = await load_cart(request, storefront, session)
        if not cart or not cart.items:
            return await render_cart(request, storefront, session, public_prefix, "Корзина пуста")
        name = clean_form_text(buyer_name, 160, required=True)
        contact = clean_form_text(buyer_contact, 160, required=True)
        email = clean_form_text(buyer_email, 254)
        safe_comment = comment.strip()[:2000]
        order = PurchaseRequest(storefront_id=storefront.id, buyer_name=name, buyer_contact=contact, buyer_email=email, comment=safe_comment, status="new")
        session.add(order)
        await session.flush()
        for item in list(cart.items):
            lot = validate_lot_for_cart(storefront, await session.get(Lot, item.lot_id), item.quantity)
            session.add(PurchaseRequestItem(purchase_request_id=order.id, lot_id=lot.id, lot_title=lot.title, price=lot.price, quantity=item.quantity))
            await session.delete(item)
        cart.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return RedirectResponse(f"{public_prefix}/order/success", status_code=303)

    async def get_purchase_request_for_user(request_id: int, user: User, session: AsyncSession) -> PurchaseRequest:
        query = (
            select(PurchaseRequest)
            .where(PurchaseRequest.id == request_id)
            .options(selectinload(PurchaseRequest.items), selectinload(PurchaseRequest.storefront))
        )
        if user.role != "admin":
            query = query.join(Storefront).where(Storefront.owner_id == user.id)
        purchase_request = (await session.execute(query)).scalar_one_or_none()
        if not purchase_request:
            raise HTTPException(status_code=404, detail="Request not found")
        return purchase_request

    @app.on_event("startup")
    async def on_startup() -> None:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        if settings.auto_create_db:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            admin = (await session.execute(select(User).where(User.username == settings.bootstrap_admin_username))).scalar_one_or_none()
            if not admin:
                if settings.app_env == "production" and settings.bootstrap_admin_password in {"admin", "password", "change-me"}:
                    raise RuntimeError("Unsafe ADMIN_PASSWORD is not allowed in production")
                session.add(User(username=settings.bootstrap_admin_username, password_hash=hash_password(settings.bootstrap_admin_password), role="admin"))
            if not await session.get(AppSetting, "base_domain"):
                session.add(AppSetting(key="base_domain", value=settings.base_domain))
            await session.commit()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request, session: AsyncSession = Depends(get_session), user: User | None = Depends(current_user)):
        base_domain = await get_base_domain(session)
        subdomain = extract_subdomain_from_host(request.headers.get("host"), base_domain)
        if subdomain:
            storefront = await get_storefront_by_subdomain(subdomain, session)
            return await render_public_storefront(request, storefront, session, "")
        if user:
            return RedirectResponse("/dashboard", status_code=303)
        return RedirectResponse("/login", status_code=303)

    @app.get("/s/{subdomain}", response_class=HTMLResponse)
    async def local_public_route(subdomain: str, request: Request, session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_by_subdomain(subdomain, session)
        return await render_public_storefront(request, storefront, session, f"/s/{storefront.subdomain}")

    @app.post("/cart/items")
    async def host_add_cart_item(request: Request, lot_id: int = Form(...), quantity: str = Form("1"), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_from_host(request, session)
        return await add_cart_item(request, storefront, lot_id, quantity, session, "")

    @app.post("/s/{subdomain}/cart/items")
    async def dev_add_cart_item(subdomain: str, request: Request, lot_id: int = Form(...), quantity: str = Form("1"), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_by_subdomain(subdomain, session)
        return await add_cart_item(request, storefront, lot_id, quantity, session, f"/s/{storefront.subdomain}")

    @app.get("/cart", response_class=HTMLResponse)
    async def host_cart(request: Request, session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_from_host(request, session)
        return await render_cart(request, storefront, session, "")

    @app.get("/s/{subdomain}/cart", response_class=HTMLResponse)
    async def dev_cart(subdomain: str, request: Request, session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_by_subdomain(subdomain, session)
        return await render_cart(request, storefront, session, f"/s/{storefront.subdomain}")

    @app.post("/cart/items/{lot_id}")
    async def host_update_cart_item(request: Request, lot_id: int, quantity: str = Form("1"), action: str = Form("update"), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_from_host(request, session)
        return await update_cart_item(request, storefront, lot_id, quantity, action, session, "")

    @app.post("/s/{subdomain}/cart/items/{lot_id}")
    async def dev_update_cart_item(subdomain: str, request: Request, lot_id: int, quantity: str = Form("1"), action: str = Form("update"), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_by_subdomain(subdomain, session)
        return await update_cart_item(request, storefront, lot_id, quantity, action, session, f"/s/{storefront.subdomain}")

    @app.get("/checkout", response_class=HTMLResponse)
    async def host_checkout_form(request: Request, session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_from_host(request, session)
        cart = await load_cart(request, storefront, session)
        return templates.TemplateResponse(request, "checkout.html", {"storefront": storefront, "items": cart.items if cart else [], "public_prefix": "", "error": None})

    @app.get("/s/{subdomain}/checkout", response_class=HTMLResponse)
    async def dev_checkout_form(subdomain: str, request: Request, session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_by_subdomain(subdomain, session)
        cart = await load_cart(request, storefront, session)
        return templates.TemplateResponse(request, "checkout.html", {"storefront": storefront, "items": cart.items if cart else [], "public_prefix": f"/s/{storefront.subdomain}", "error": None})

    @app.post("/checkout")
    async def host_checkout(request: Request, buyer_name: str = Form(...), buyer_contact: str = Form(...), buyer_email: str = Form(""), comment: str = Form(""), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_from_host(request, session)
        return await create_purchase_request_from_cart(request, storefront, buyer_name, buyer_contact, buyer_email, comment, session, "")

    @app.post("/s/{subdomain}/checkout")
    async def dev_checkout(subdomain: str, request: Request, buyer_name: str = Form(...), buyer_contact: str = Form(...), buyer_email: str = Form(""), comment: str = Form(""), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_by_subdomain(subdomain, session)
        return await create_purchase_request_from_cart(request, storefront, buyer_name, buyer_contact, buyer_email, comment, session, f"/s/{storefront.subdomain}")

    @app.get("/order/success", response_class=HTMLResponse)
    async def host_order_success(request: Request, session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_from_host(request, session)
        return templates.TemplateResponse(request, "order_success.html", {"storefront": storefront, "public_prefix": ""})

    @app.get("/s/{subdomain}/order/success", response_class=HTMLResponse)
    async def dev_order_success(subdomain: str, request: Request, session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_by_subdomain(subdomain, session)
        return templates.TemplateResponse(request, "order_success.html", {"storefront": storefront, "public_prefix": f"/s/{storefront.subdomain}"})

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request):
        return templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login")
    async def login(request: Request, username: str = Form(...), password: str = Form(...), session: AsyncSession = Depends(get_session)):
        user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(request, "login.html", {"error": "Неверный логин или пароль"}, status_code=400)
        request.session.clear()
        request.session["user_id"] = user.id
        return RedirectResponse("/dashboard", status_code=303)

    @app.post("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        query = select(Storefront).order_by(Storefront.id)
        if user.role != "admin":
            query = query.where(Storefront.owner_id == user.id)
        storefronts = (await session.execute(query)).scalars().all()
        return templates.TemplateResponse(request, "dashboard.html", {"user": user, "storefronts": storefronts, "base_domain": await get_base_domain(session), "error": None})

    @app.post("/storefronts")
    async def create_storefront(request: Request, subdomain: str = Form(...), user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        if user.role not in {"admin", "owner"}:
            raise HTTPException(status_code=403, detail="Viewer cannot create storefronts")
        try:
            normalized = validate_subdomain(subdomain)
        except ValueError as exc:
            storefronts = (await session.execute(select(Storefront).where(Storefront.owner_id == user.id))).scalars().all()
            return templates.TemplateResponse(request, "dashboard.html", {"user": user, "storefronts": storefronts, "base_domain": await get_base_domain(session), "error": str(exc)}, status_code=400)
        owner_id = user.id
        user_view = {"id": user.id, "username": user.username, "role": user.role}
        storefront = Storefront(owner_id=owner_id, subdomain=normalized, title=normalized.capitalize())
        session.add(storefront)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            storefronts = (await session.execute(select(Storefront).where(Storefront.owner_id == owner_id))).scalars().all()
            return templates.TemplateResponse(request, "dashboard.html", {"user": user_view, "storefronts": storefronts, "base_domain": await get_base_domain(session), "error": "Subdomain already exists"}, status_code=409)
        return RedirectResponse(f"/storefronts/{storefront.id}", status_code=303)

    @app.get("/storefronts/{storefront_id}", response_class=HTMLResponse)
    async def storefront_editor(storefront_id: int, request: Request, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_for_owner(storefront_id, user, session)
        return templates.TemplateResponse(request, "storefront_editor.html", {"user": user, "storefront": storefront, "base_domain": await get_base_domain(session), "error": None})

    @app.post("/storefronts/{storefront_id}")
    async def update_storefront(
        storefront_id: int,
        request: Request,
        title: str = Form(...),
        description: str = Form(""),
        seo_title: str = Form(""),
        seo_description: str = Form(""),
        is_published: str | None = Form(None),
        banner: UploadFile | None = File(None),
        user: User = Depends(require_user),
        session: AsyncSession = Depends(get_session),
    ):
        storefront = await get_storefront_for_owner(storefront_id, user, session)
        image = await save_image(banner, user, session, storefront.id)
        if image:
            storefront.banner_image_id = image.id
        storefront.title = title.strip()[:160] or storefront.subdomain.capitalize()
        storefront.description = description.strip()
        storefront.seo_title = seo_title.strip()[:180]
        storefront.seo_description = seo_description.strip()[:320]
        storefront.is_published = bool(is_published)
        storefront.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return RedirectResponse(f"/storefronts/{storefront.id}", status_code=303)

    @app.get("/storefronts/{storefront_id}/lots/new", response_class=HTMLResponse)
    async def lot_new_form(storefront_id: int, request: Request, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_for_owner(storefront_id, user, session)
        return templates.TemplateResponse(request, "lot_form.html", {"user": user, "storefront": storefront, "lot": None, "error": None})

    @app.post("/storefronts/{storefront_id}/lots")
    async def create_lot(
        storefront_id: int,
        title: str = Form(...),
        description: str = Form(""),
        price: str = Form(...),
        quantity: str | None = Form(None),
        infinite_quantity: str | None = Form(None),
        is_published: str | None = Form(None),
        image: UploadFile | None = File(None),
        user: User = Depends(require_user),
        session: AsyncSession = Depends(get_session),
    ):
        storefront = await get_storefront_for_owner(storefront_id, user, session)
        uploaded = await save_image(image, user, session, storefront.id)
        session.add(Lot(storefront_id=storefront.id, image_id=uploaded.id if uploaded else None, title=title.strip()[:160] or "Без названия", description=description.strip(), price=parse_price(price), quantity=parse_quantity(infinite_quantity, quantity), is_published=bool(is_published)))
        await session.commit()
        return RedirectResponse(f"/storefronts/{storefront.id}", status_code=303)

    @app.get("/storefronts/{storefront_id}/lots/{lot_id}/edit", response_class=HTMLResponse)
    async def lot_edit_form(storefront_id: int, lot_id: int, request: Request, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_for_owner(storefront_id, user, session)
        lot = await session.get(Lot, lot_id, options=[selectinload(Lot.image)])
        if not lot or lot.storefront_id != storefront.id:
            raise HTTPException(status_code=404, detail="Lot not found")
        return templates.TemplateResponse(request, "lot_form.html", {"user": user, "storefront": storefront, "lot": lot, "error": None})

    @app.post("/storefronts/{storefront_id}/lots/{lot_id}")
    async def update_lot(
        storefront_id: int,
        lot_id: int,
        title: str = Form(...),
        description: str = Form(""),
        price: str = Form(...),
        quantity: str | None = Form(None),
        infinite_quantity: str | None = Form(None),
        is_published: str | None = Form(None),
        image: UploadFile | None = File(None),
        user: User = Depends(require_user),
        session: AsyncSession = Depends(get_session),
    ):
        storefront = await get_storefront_for_owner(storefront_id, user, session)
        lot = await session.get(Lot, lot_id)
        if not lot or lot.storefront_id != storefront.id:
            raise HTTPException(status_code=404, detail="Lot not found")
        uploaded = await save_image(image, user, session, storefront.id)
        if uploaded:
            lot.image_id = uploaded.id
        lot.title = title.strip()[:160] or "Без названия"
        lot.description = description.strip()
        lot.price = parse_price(price)
        lot.quantity = parse_quantity(infinite_quantity, quantity)
        lot.is_published = bool(is_published)
        lot.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return RedirectResponse(f"/storefronts/{storefront.id}", status_code=303)

    @app.post("/storefronts/{storefront_id}/lots/{lot_id}/delete")
    async def delete_lot(storefront_id: int, lot_id: int, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        storefront = await get_storefront_for_owner(storefront_id, user, session)
        lot = await session.get(Lot, lot_id)
        if not lot or lot.storefront_id != storefront.id:
            raise HTTPException(status_code=404, detail="Lot not found")
        await session.delete(lot)
        await session.commit()
        return RedirectResponse(f"/storefronts/{storefront.id}", status_code=303)

    @app.get("/requests", response_class=HTMLResponse)
    async def requests_list(request: Request, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        query = select(PurchaseRequest).options(selectinload(PurchaseRequest.storefront), selectinload(PurchaseRequest.items)).order_by(PurchaseRequest.id.desc())
        if user.role != "admin":
            query = query.join(Storefront).where(Storefront.owner_id == user.id)
        purchase_requests = (await session.execute(query)).scalars().all()
        return templates.TemplateResponse(request, "requests.html", {"user": user, "requests": purchase_requests})

    @app.get("/requests/{request_id}", response_class=HTMLResponse)
    async def request_detail(request_id: int, request: Request, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        purchase_request = await get_purchase_request_for_user(request_id, user, session)
        return templates.TemplateResponse(request, "request_detail.html", {"user": user, "request_item": purchase_request, "statuses": sorted(REQUEST_STATUSES)})

    @app.post("/requests/{request_id}/status")
    async def update_request_status(request_id: int, status_value: str = Form(...), user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        if status_value not in REQUEST_STATUSES:
            raise HTTPException(status_code=400, detail="Unknown request status")
        purchase_request = await get_purchase_request_for_user(request_id, user, session)
        purchase_request.status = status_value
        purchase_request.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return RedirectResponse(f"/requests/{purchase_request.id}", status_code=303)

    @app.get("/procurement", response_class=HTMLResponse)
    async def procurement(request: Request, user: User = Depends(require_user), session: AsyncSession = Depends(get_session)):
        query = (
            select(PurchaseRequest)
            .where(PurchaseRequest.status.in_(PROCUREMENT_STATUSES))
            .options(selectinload(PurchaseRequest.items), selectinload(PurchaseRequest.storefront))
            .order_by(PurchaseRequest.id)
        )
        if user.role != "admin":
            query = query.join(Storefront).where(Storefront.owner_id == user.id)
        purchase_requests = (await session.execute(query)).scalars().all()
        lot_ids = {item.lot_id for pr in purchase_requests for item in pr.items if item.lot_id is not None}
        lots_by_id: dict[int, Lot] = {}
        if lot_ids:
            lots_by_id = {lot.id: lot for lot in (await session.execute(select(Lot).where(Lot.id.in_(lot_ids)))).scalars().all()}
        aggregated: dict[tuple[int, int | None], dict[str, object]] = {}
        for pr in purchase_requests:
            for item in pr.items:
                key = (pr.storefront_id, item.lot_id)
                row = aggregated.setdefault(
                    key,
                    {
                        "storefront": pr.storefront,
                        "lot_title": item.lot_title,
                        "quantity": 0,
                        "available_quantity": lots_by_id[item.lot_id].quantity if item.lot_id in lots_by_id else None,
                        "estimated_total": Decimal("0.00"),
                        "request_ids": [],
                    },
                )
                row["quantity"] = int(row["quantity"]) + item.quantity
                row["estimated_total"] = Decimal(row["estimated_total"]) + item.price * item.quantity
                row["request_ids"] = [*row["request_ids"], pr.id]
        return templates.TemplateResponse(request, "procurement.html", {"user": user, "rows": list(aggregated.values())})

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_form(request: Request, user: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
        return templates.TemplateResponse(request, "settings.html", {"user": user, "base_domain": await get_base_domain(session), "error": None})

    @app.post("/settings")
    async def update_settings(request: Request, base_domain: str = Form(...), user: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
        try:
            normalized = normalize_domain(base_domain)
        except ValueError as exc:
            return templates.TemplateResponse(request, "settings.html", {"user": user, "base_domain": base_domain, "error": str(exc)}, status_code=400)
        setting = await session.get(AppSetting, "base_domain")
        if setting:
            setting.value = normalized
        else:
            session.add(AppSetting(key="base_domain", value=normalized))
        await session.commit()
        return RedirectResponse("/settings", status_code=303)

    @app.get("/uploads/{image_id}")
    async def uploaded_image(image_id: int, session: AsyncSession = Depends(get_session)):
        image = await session.get(UploadedImage, image_id)
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        path = ensure_child_path(settings.upload_dir, image.stored_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Image file not found")
        return FileResponse(path, media_type=image.content_type, filename=image.original_filename)

    return app


create_app = build_app
