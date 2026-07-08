"""email OTP: attempts counter on login_token

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # login_token now stores OTP code hashes instead of magic-link token hashes;
    # attempts counts failed verifications (the code locks at the cap)
    op.execute("ALTER TABLE login_token ADD COLUMN attempts int NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE login_token DROP COLUMN attempts")
