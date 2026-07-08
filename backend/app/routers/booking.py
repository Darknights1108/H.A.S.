"""Candidate booking API (no login; authorised by application.booking_token).

State flow:
  pick a slot (hold; free to withdraw/re-pick) -> confirm (creates the interview + confirmation email) -> later changes go through reschedule
Concurrency: every slot mutation takes a SELECT ... FOR UPDATE row lock before validating state.
"""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Candidate, Interview, Interviewer, Slot, SlotInterviewer
import logging

from ..services.mailer import send_raw, try_send_draft
from ..services.scheduling import (
    confirmation_email_body,
    draft_email,
    get_setting_int,
    release_slot,
    slot_label,
)

logger = logging.getLogger(__name__)


def _notify_panel(db: Session, slot: Slot, candidate: Candidate,
                  meeting_link: str | None, rescheduled: bool) -> int:
    """Notify the slot's panel interviewers about the booking; best-effort, never blocks the flow."""
    emails = db.scalars(
        select(Interviewer.email)
        .join(SlotInterviewer, SlotInterviewer.interviewer_id == Interviewer.id)
        .where(SlotInterviewer.slot_id == slot.id)
    ).all()
    verb = "rescheduled to" if rescheduled else "booked"
    subject = f"Interview {verb} {slot_label(slot)} — {candidate.name}"
    body = (
        f"Hi,\n\n"
        f"{candidate.name} ({candidate.email}) has {verb} your interview slot.\n\n"
        f"When: {slot_label(slot)}\n"
        f"Join link: {meeting_link or 'TBA'}\n\n"
        f"You can view your schedule in the HAS dashboard.\n"
    )
    sent = 0
    for em in emails:
        try:
            send_raw(em, subject, body)
            sent += 1
        except Exception as e:
            logger.info("panel notification to %s skipped: %s", em, e)
    return sent

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
        if s.slot_date.weekday() < 5  # interviews on working days only (Mon-Fri)
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
                "reschedule_max": get_setting_int(db, "reschedule_max", 0),  # 0 = unlimited
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
    """Row-lock + validate + book; caller commits. Returns the newly booked slot."""
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise HTTPException(404, "slot not found")
    if slot.status != "open":
        raise HTTPException(409, "slot no longer available, please pick another")
    # release the slot this candidate already holds (withdraw & re-pick)
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
    """Contact details the candidate fills/corrects at confirmation (Bookings-style 'Add your details')."""

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
    # Update candidate details (email changes need a uniqueness check — it's the identity key)
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
    # placeholder meeting link; swap for Google Meet / Teams later
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
    try_send_draft(db, email)  # factual content, auto-send; failure keeps the draft for manual re-send
    db.commit()
    notified = _notify_panel(db, held, candidate, meeting_link, rescheduled=False)
    return {
        "confirmed": True,
        "meeting_link": meeting_link,
        "slot": _slot_view(db, held),
        "interviewers_notified": notified,
    }


class RescheduleIn(BaseModel):
    slot_id: uuid.UUID


@router.post("/{token}/reschedule")
def reschedule(token: uuid.UUID, payload: RescheduleIn, db: Session = Depends(get_db)) -> dict:
    app_ = _get_application(db, token)
    interview = _active_interview(db, app_.id)
    if interview is None:
        raise HTTPException(409, "no confirmed interview to reschedule")
    max_ = get_setting_int(db, "reschedule_max", 0)  # 0 = unlimited
    if max_ > 0 and interview.reschedule_count >= max_:
        raise HTTPException(409, f"reschedule limit reached ({max_})")
    slot = _book_slot(db, app_, payload.slot_id)  # releases the old slot internally
    interview.slot_id = slot.id
    interview.reschedule_count += 1
    candidate = db.get(Candidate, app_.candidate_id)
    subject, body = confirmation_email_body(
        db, candidate, slot, interview.meeting_link, rescheduled=True
    )
    email = draft_email(db, app_, "reschedule", subject, body)
    db.flush()
    try_send_draft(db, email)  # same as the confirmation email: auto-send, failure keeps the draft
    db.commit()
    notified = _notify_panel(db, slot, candidate, interview.meeting_link, rescheduled=True)
    return {
        "confirmed": True,
        "slot": _slot_view(db, slot),
        "reschedule_count": interview.reschedule_count,
        "reschedule_max": max_,
        "interviewers_notified": notified,
    }
