"""排期模块共用逻辑:设置读取、时段释放、邮件草稿。"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AppSetting, Application, Candidate, EmailLog, Slot, SlotInterviewer


def get_setting_int(db: Session, key: str, default: int) -> int:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return default


def interviewer_count(db: Session, slot_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(SlotInterviewer).where(SlotInterviewer.slot_id == slot_id)
    ) or 0


def release_slot(db: Session, slot: Slot) -> None:
    """候选人撤回/改期后释放时段:回到 open(仍有面试官)或 empty。"""
    slot.candidate_id = None
    slot.status = "open" if interviewer_count(db, slot.id) > 0 else "empty"


def recompute_unbooked_status(db: Session, slot: Slot) -> None:
    """面试官认领/撤回后刷新未被预订时段的状态。"""
    if slot.status == "booked":
        return
    slot.status = "open" if interviewer_count(db, slot.id) > 0 else "empty"


def draft_email(
    db: Session, application: Application, type_: str, subject: str, body: str
) -> EmailLog:
    email = EmailLog(
        application_id=application.id, type=type_, subject=subject, body=body, status="draft"
    )
    db.add(email)
    return email


def slot_label(slot: Slot) -> str:
    return f"{slot.slot_date.isoformat()} {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')} (MYT)"


def confirmation_email_body(
    db: Session, candidate: Candidate, slot: Slot, meeting_link: str, rescheduled: bool
) -> tuple[str, str]:
    names = db.scalars(
        select(SlotInterviewer).where(SlotInterviewer.slot_id == slot.id)
    ).all()
    from ..models import Interviewer  # local import to avoid cycle noise

    interviewer_names = db.scalars(
        select(Interviewer.name).join(
            SlotInterviewer, SlotInterviewer.interviewer_id == Interviewer.id
        ).where(SlotInterviewer.slot_id == slot.id)
    ).all()
    _ = names
    verb = "rescheduled" if rescheduled else "confirmed"
    subject = f"Your interview is {verb} — {slot_label(slot)}"
    body = (
        f"Hi {candidate.name},\n\n"
        f"Your online interview has been {verb}.\n\n"
        f"When: {slot_label(slot)}\n"
        f"With: {', '.join(interviewer_names) or 'TBA'}\n"
        f"Join link: {meeting_link}\n\n"
        f"Need to change the time? Use your booking link to reschedule.\n"
    )
    return subject, body
