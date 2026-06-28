"""add_telegram_message_log

Revision ID: f2b4a0c7d9e1
Revises: d6ab942a8d7c
Create Date: 2026-06-28 01:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2b4a0c7d9e1"
down_revision: Union[str, None] = "d6ab942a8d7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "telegram_message_log" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "telegram_message_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("chat_id", sa.Integer(), nullable=True),
        sa.Column("message_type", sa.String(), nullable=False, server_default="message"),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("telegram_message_log")
