"""SQLAlchemy ORM models — mirror db/schema.sql.

注意:v1 的建表/枚举/触发器由 Alembic 初始迁移直接执行 schema.sql 完成,
这里的 model 仅用于应用层查询。PG 枚举类型用 create_type=False 引用已存在的类型。
"""

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# --- 引用 schema.sql 中已创建的枚举类型(不重复创建)---
application_status = ENUM(
    "applied", "scored", "shortlisted", "scheduled", "interviewed", "passed", "rejected",
    name="application_status", create_type=False,
)
score_band = ENUM("high", "medium", "low", name="score_band", create_type=False)
slot_status = ENUM("empty", "open", "booked", name="slot_status", create_type=False)
interview_status = ENUM(
    "scheduled", "completed", "passed", "failed", "cancelled",
    name="interview_status", create_type=False,
)
email_type = ENUM("invite", "offer", "reject", name="email_type", create_type=False)
email_status = ENUM("draft", "sent", name="email_status", create_type=False)

_uuid_pk = lambda: mapped_column(  # noqa: E731
    UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
)
_now = lambda: mapped_column(  # noqa: E731
    DateTime(timezone=True), nullable=False, server_default=text("now()")
)


class AppSetting(Base):
    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime.datetime] = _now()


class Candidate(Base):
    __tablename__ = "candidate"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(Text)
    consent_talent_bank: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime.datetime] = _now()


class Job(Base):
    __tablename__ = "job"
    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = _now()


class Application(Base):
    __tablename__ = "application"
    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job.id", ondelete="RESTRICT"), nullable=False
    )
    cgpa: Mapped[float | None] = mapped_column(Numeric(3, 2))
    degree_field: Mapped[str | None] = mapped_column(Text)
    is_fulltime: Mapped[bool | None] = mapped_column(Boolean)
    prog_langs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    has_sql: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_ai_study: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    eca: Mapped[str | None] = mapped_column(Text)
    resume_file_url: Mapped[str | None] = mapped_column(Text)
    form_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        application_status, nullable=False, server_default=text("'applied'")
    )
    shortlisted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime.datetime] = _now()
    updated_at: Mapped[datetime.datetime] = _now()


class Score(Base):
    __tablename__ = "score"
    id: Mapped[uuid.UUID] = _uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    knockout_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    band: Mapped[str] = mapped_column(score_band, nullable=False)
    total_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    breakdown: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    reasoning: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = _now()


class Interviewer(Base):
    __tablename__ = "interviewer"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime.datetime] = _now()


class Slot(Base):
    __tablename__ = "slot"
    id: Mapped[uuid.UUID] = _uuid_pk()
    slot_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        slot_status, nullable=False, server_default=text("'empty'")
    )
    created_at: Mapped[datetime.datetime] = _now()


class SlotInterviewer(Base):
    __tablename__ = "slot_interviewer"
    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slot.id", ondelete="CASCADE"), primary_key=True
    )
    interviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviewer.id", ondelete="CASCADE"), primary_key=True
    )
    claimed_at: Mapped[datetime.datetime] = _now()


class Interview(Base):
    __tablename__ = "interview"
    id: Mapped[uuid.UUID] = _uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), nullable=False
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slot.id", ondelete="RESTRICT"), nullable=False
    )
    meeting_link: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        interview_status, nullable=False, server_default=text("'scheduled'")
    )
    reschedule_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = _now()


class EmailLog(Base):
    __tablename__ = "email_log"
    id: Mapped[uuid.UUID] = _uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(email_type, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        email_status, nullable=False, server_default=text("'draft'")
    )
    created_at: Mapped[datetime.datetime] = _now()
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
