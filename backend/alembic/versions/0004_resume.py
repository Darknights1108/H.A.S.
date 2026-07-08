"""resume parsing: parsed jsonb + parse status on application

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # resume_file_url already exists (MinIO object key); add parse result and status here
    op.execute(
        """
        ALTER TABLE application
            ADD COLUMN resume_parsed jsonb,
            ADD COLUMN resume_parse_status text NOT NULL DEFAULT 'none'
                CHECK (resume_parse_status IN ('none', 'pending', 'done', 'failed'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE application DROP COLUMN resume_parsed, DROP COLUMN resume_parse_status"
    )
