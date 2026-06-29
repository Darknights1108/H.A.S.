"""initial schema — 直接执行 db/schema.sql(含枚举、约束、触发器、设置 seed)

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
    # 优先用环境变量(docker 镜像内),否则按相对路径定位 repo 根的 db/schema.sql
    env_path = os.environ.get("HAS_SCHEMA_SQL")
    if env_path:
        path = Path(env_path)
    else:
        path = Path(__file__).resolve().parents[3] / "db" / "schema.sql"
    return path.read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_schema_sql())


def downgrade() -> None:
    # baseline 迁移:开发环境下整体重置 public schema
    op.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
