"""cart and purchase request workflow

Revision ID: 20260701_0002
Revises: 20260701_0001
Create Date: 2026-07-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260701_0002"
down_revision = "20260701_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storefront_id", "token_hash", name="uq_carts_storefront_token"),
    )
    op.create_index("ix_carts_storefront_id", "carts", ["storefront_id"])
    op.create_index("ix_carts_token_hash", "carts", ["token_hash"])

    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cart_id", sa.Integer(), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("cart_id", "lot_id", name="uq_cart_items_cart_lot"),
    )
    op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])
    op.create_index("ix_cart_items_lot_id", "cart_items", ["lot_id"])

    op.create_table(
        "purchase_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_name", sa.String(length=160), nullable=False),
        sa.Column("buyer_contact", sa.String(length=160), nullable=False),
        sa.Column("buyer_email", sa.String(length=254), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_purchase_requests_storefront_id", "purchase_requests", ["storefront_id"])
    op.create_index("ix_purchase_requests_status", "purchase_requests", ["status"])

    op.create_table(
        "purchase_request_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_request_id", sa.Integer(), sa.ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_title", sa.String(length=160), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
    )
    op.create_index("ix_purchase_request_items_purchase_request_id", "purchase_request_items", ["purchase_request_id"])
    op.create_index("ix_purchase_request_items_lot_id", "purchase_request_items", ["lot_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_request_items_lot_id", table_name="purchase_request_items")
    op.drop_index("ix_purchase_request_items_purchase_request_id", table_name="purchase_request_items")
    op.drop_table("purchase_request_items")
    op.drop_index("ix_purchase_requests_status", table_name="purchase_requests")
    op.drop_index("ix_purchase_requests_storefront_id", table_name="purchase_requests")
    op.drop_table("purchase_requests")
    op.drop_index("ix_cart_items_lot_id", table_name="cart_items")
    op.drop_index("ix_cart_items_cart_id", table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_index("ix_carts_token_hash", table_name="carts")
    op.drop_index("ix_carts_storefront_id", table_name="carts")
    op.drop_table("carts")
