"""initial schema — executes db/schema.sql directly (enums, constraints, triggers, setting seeds)

Revision ID: 0001
Revises:
Create Date: 2026-06-29
"""
import os
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _schema_sql() -> str:
    # Prefer the env var (inside the docker image); otherwise locate db/schema.sql relative to the repo root
    env_path = os.environ.get("HAS_SCHEMA_SQL")
    if env_path:
        path = Path(env_path)
    else:
        path = Path(__file__).resolve().parents[3] / "db" / "schema.sql"
    return path.read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_schema_sql())


def downgrade() -> None:
    # baseline migration: in dev, reset the whole public schema
    op.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
