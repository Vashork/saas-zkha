"""backfill_payment_transactions

Revision ID: d6ab942a8d7c
Revises: b3b26935f1bf
Create Date: 2026-06-26 17:17:03.949021

Backfills PaymentTransaction rows for legacy Payment records that have
paid_amount > 0 but no child transactions yet.  Idempotent — safe to
run multiple times.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d6ab942a8d7c"
down_revision: Union[str, None] = "b3b26935f1bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO payment_transactions (id, payment_id, amount, paid_date, receipt_file, notes)
        SELECT
            'tx-backfill-' || p.id,
            p.id,
            p.paid_amount,
            COALESCE(p.paid_date, p.due_date),
            p.receipt_file,
            'Backfilled from legacy payment fields'
        FROM payments p
        WHERE p.paid_amount IS NOT NULL
          AND p.paid_amount > 0
          AND NOT EXISTS (
              SELECT 1 FROM payment_transactions t WHERE t.payment_id = p.id
          )
    """)


def downgrade() -> None:
    # Remove only the backfilled rows (identified by id prefix).
    op.execute("""
        DELETE FROM payment_transactions
        WHERE id LIKE 'tx-backfill-%'
          AND notes = 'Backfilled from legacy payment fields'
    """)
