"""候选人端预约 API(免登录,凭 application.booking_token)。

状态流:
  选时段(hold,可自由撤回改选)→ 确认(生成 interview + 确认信草稿)→ 之后改时间走 reschedule(限次)
并发:所有改动 slot 的操作先 SELECT ... FOR UPDATE 行锁,再校验状态。
"""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Candidate, Interview, Interviewer, Slot, SlotInterviewer
from ..services.mailer import try_send_draft
from ..services.scheduling import (
    confirmation_email_body,
    draft_email,
    get_setting_int,
    release_slot,
)

router = APIRouter(prefix="/booking", tags=["booking"])


def _get_application(db: Session, token: uuid.UUID) -> Application:
    app_ = db.scalar(select(Application).where(Application.booking_token == token))
    if app_ is None:
        raise HTTPException(404, "booking not found")
    return app_


def _held_slot(db: Session, candidate_id: uuid.UUID, for_update: bool = False) -> Slot | None:
    stmt = select(Slot).where(Slot.candidate_id == candidate_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _active_interview(db: Session, application_id: uuid.UUID) -> Interview | None:
    return db.scalar(
        select(Interview).where(
            Interview.application_id == application_id,
            Interview.status == "scheduled",
        )
    )


def _slot_view(db: Session, slot: Slot) -> dict:
    names = db.scalars(
        select(Interviewer.name)
        .join(SlotInterviewer, SlotInterviewer.interviewer_id == Interviewer.id)
        .where(SlotInterviewer.slot_id == slot.id)
    ).all()
    return {
        "id": str(slot.id),
        "date": slot.slot_date.isoformat(),
        "start": slot.start_time.strftime("%H:%M"),
        "end": slot.end_time.strftime("%H:%M"),
        "interviewers": list(names),
    }


@router.get("/{token}")
def get_booking(token: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    app_ = _get_application(db, token)
    candidate = db.get(Candidate, app_.candidate_id)
    held = _held_slot(db, app_.candidate_id)
    interview = _active_interview(db, app_.id)
    today = datetime.date.today()
    open_slots = [
        s
        for s in db.scalars(
            select(Slot)
            .where(Slot.status == "open", Slot.slot_date >= today)
            .order_by(Slot.slot_date, Slot.start_time)
        )
        if s.slot_date.weekday() < 5  # 面试只在工作日(周一至五)
    ]
    return {
        "candidate": {"name": candidate.name, "email": candidate.email, "phone": candidate.phone},
        "application_status": app_.status,
        "held_slot": _slot_view(db, held) if held else None,
        "confirmed": interview is not None,
        "interview": (
            {
                "meeting_link": interview.meeting_link,
                "reschedule_count": interview.reschedule_count,
                "reschedule_max": get_setting_int(db, "reschedule_max", 1),
            }
            if interview
            else None
        ),
        "open_slots": [_slot_view(db, s) for s in open_slots],
        "timezone": "(UTC+08:00) Kuala Lumpur (MYT)",
    }


class SelectIn(BaseModel):
    slot_id: uuid.UUID


def _book_slot(db: Session, app_: Application, slot_id: uuid.UUID) -> Slot:
    """行锁 + 校验 + 落定预订;调用方负责 commit。返回新预订的 slot。"""
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise HTTPException(404, "slot not found")
    if slot.status != "open":
        raise HTTPException(409, "slot no longer available, please pick another")
    # 释放该候选人已持有的时段(撤回改选)
    prev = _held_slot(db, app_.candidate_id, for_update=True)
    if prev is not None:
        release_slot(db, prev)
        db.flush()
    slot.candidate_id = app_.candidate_id
    slot.status = "booked"
    return slot


@router.post("/{token}/select")
def select_slot(token: uuid.UUID, payload: SelectIn, db: Session = Depends(get_db)) -> dict:
    app_ = _get_application(db, token)
    if app_.status not in ("shortlisted", "scheduled"):
        raise HTTPException(409, f"application not in a bookable state ({app_.status})")
    if _active_interview(db, app_.id):
        raise HTTPException(409, "interview already confirmed — use reschedule instead")
    slot = _book_slot(db, app_, payload.slot_id)
    db.commit()
    return {"held_slot": _slot_view(db, slot), "confirmed": False}


@router.post("/{token}/withdraw")
def withdraw(token: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    app_ = _get_application(db, token)
    if _active_interview(db, app_.id):
        raise HTTPException(409, "interview already confirmed — use reschedule instead")
    held = _held_slot(db, app_.candidate_id, for_update=True)
    if held is None:
        raise HTTPException(409, "no slot held")
    release_slot(db, held)
    db.commit()
    return {"held_slot": None}


class ConfirmIn(BaseModel):
    """候选人在确认时填写/修正的联系资料(Bookings 式 Add your details)。"""

    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


@router.post("/{token}/confirm")
def confirm(
    token: uuid.UUID, payload: ConfirmIn | None = None, db: Session = Depends(get_db)
) -> dict:
    app_ = _get_application(db, token)
    if _active_interview(db, app_.id):
        raise HTTPException(409, "already confirmed")
    held = _held_slot(db, app_.candidate_id, for_update=True)
    if held is None:
        raise HTTPException(409, "select a slot first")
    candidate = db.get(Candidate, app_.candidate_id)
    # 更新候选人资料(email 变更需查重,它是身份键)
    if payload:
        if payload.email and payload.email != candidate.email:
            taken = db.scalar(
                select(Candidate).where(
                    Candidate.email == payload.email, Candidate.id != candidate.id
                )
            )
            if taken:
                raise HTTPException(409, "this email is already used by another candidate")
            candidate.email = payload.email
        if payload.name and payload.name.strip():
            candidate.name = payload.name.strip()
        if payload.phone is not None:
            candidate.phone = payload.phone.strip() or None
    # 占位会议链接;后续接 Google Meet / Teams 时替换
    meeting_link = f"https://meet.jit.si/HAS-{app_.booking_token}"
    interview = Interview(
        application_id=app_.id,
        slot_id=held.id,
        meeting_link=meeting_link,
        status="scheduled",
        confirmed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(interview)
    app_.status = "scheduled"
    subject, body = confirmation_email_body(db, candidate, held, meeting_link, rescheduled=False)
    email = draft_email(db, app_, "confirmation", subject, body)
    db.flush()
    try_send_draft(db, email)  # 纯事实性内容,自动发送;失败保留草稿可人工重发
    db.commit()
    return {
        "confirmed": True,
        "meeting_link": meeting_link,
        "slot": _slot_view(db, held),
    }


class RescheduleIn(BaseModel):
    slot_id: uuid.UUID


@router.post("/{token}/reschedule")
def reschedule(token: uuid.UUID, payload: RescheduleIn, db: Session = Depends(get_db)) -> dict:
    app_ = _get_application(db, token)
    interview = _active_interview(db, app_.id)
    if interview is None:
        raise HTTPException(409, "no confirmed interview to reschedule")
    max_ = get_setting_int(db, "reschedule_max", 1)
    if interview.reschedule_count >= max_:
        raise HTTPException(409, f"reschedule limit reached ({max_})")
    slot = _book_slot(db, app_, payload.slot_id)  # 内部会释放旧时段
    interview.slot_id = slot.id
    interview.reschedule_count += 1
    candidate = db.get(Candidate, app_.candidate_id)
    subject, body = confirmation_email_body(
        db, candidate, slot, interview.meeting_link, rescheduled=True
    )
    email = draft_email(db, app_, "reschedule", subject, body)
    db.flush()
    try_send_draft(db, email)  # 同确认信:自动发送,失败保留草稿
    db.commit()
    return {
        "confirmed": True,
        "slot": _slot_view(db, slot),
        "reschedule_count": interview.reschedule_count,
        "reschedule_max": max_,
    }
