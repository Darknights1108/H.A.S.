"""scheduling: booking token + confirmation/reschedule email types

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Unique token for unauthenticated candidate access to the booking page (shared by invite link / reschedule)
    op.execute(
        """
        ALTER TABLE application
            ADD COLUMN booking_token uuid NOT NULL UNIQUE DEFAULT gen_random_uuid()
        """
    )
    # New email types: booking confirmation / reschedule (PG12+ allows ADD VALUE inside a transaction, just not using it in the same one)
    op.execute("ALTER TYPE email_type ADD VALUE IF NOT EXISTS 'confirmation'")
    op.execute("ALTER TYPE email_type ADD VALUE IF NOT EXISTS 'reschedule'")


def downgrade() -> None:
    op.execute("ALTER TABLE application DROP COLUMN booking_token")
    # PG cannot remove enum values; to roll back in dev, rebuild the enum or reset entirely
