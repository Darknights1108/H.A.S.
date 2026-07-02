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
    # 候选人免登录访问预约页的唯一 token(邀请链接 / 改期共用)
    op.execute(
        """
        ALTER TABLE application
            ADD COLUMN booking_token uuid NOT NULL UNIQUE DEFAULT gen_random_uuid()
        """
    )
    # 新邮件类型:预约确认 / 改期确认(PG12+ 允许在事务内 ADD VALUE,只是同事务内不能使用)
    op.execute("ALTER TYPE email_type ADD VALUE IF NOT EXISTS 'confirmation'")
    op.execute("ALTER TYPE email_type ADD VALUE IF NOT EXISTS 'reschedule'")


def downgrade() -> None:
    op.execute("ALTER TABLE application DROP COLUMN booking_token")
    # PG 不支持从枚举移除值;开发期如需回退,重建枚举或整体 reset
