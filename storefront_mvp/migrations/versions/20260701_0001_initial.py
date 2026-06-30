"""initial storefront builder schema

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260701_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )

    op.create_table(
        "storefronts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subdomain", sa.String(length=63), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("banner_image_id", sa.Integer(), nullable=True),
        sa.Column("seo_title", sa.String(length=180), nullable=False),
        sa.Column("seo_description", sa.String(length=320), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("subdomain", name="uq_storefronts_subdomain"),
    )
    op.create_index("ix_storefronts_owner_id", "storefronts", ["owner_id"])
    op.create_index("ix_storefronts_subdomain", "storefronts", ["subdomain"])

    op.create_table(
        "uploaded_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stored_path", name="uq_uploaded_images_stored_path"),
    )
    op.create_index("ix_uploaded_images_owner_id", "uploaded_images", ["owner_id"])
    op.create_index("ix_uploaded_images_storefront_id", "uploaded_images", ["storefront_id"])

    op.create_table(
        "lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("uploaded_images.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lots_storefront_id", "lots", ["storefront_id"])


def downgrade() -> None:
    op.drop_index("ix_lots_storefront_id", table_name="lots")
    op.drop_table("lots")
    op.drop_index("ix_uploaded_images_storefront_id", table_name="uploaded_images")
    op.drop_index("ix_uploaded_images_owner_id", table_name="uploaded_images")
    op.drop_table("uploaded_images")
    op.drop_index("ix_storefronts_subdomain", table_name="storefronts")
    op.drop_index("ix_storefronts_owner_id", table_name="storefronts")
    op.drop_table("storefronts")
    op.drop_table("app_settings")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
