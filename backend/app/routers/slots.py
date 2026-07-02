"""管理端排期 API:面试官管理、时段网格生成、认领/撤回。

暂无认证(当前全系统仅 admin 角色);interviewer_id 由请求体传入。
"""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Interviewer, Slot, SlotInterviewer
from ..services.scheduling import get_setting_int, recompute_unbooked_status

router = APIRouter(prefix="/slots", tags=["slots"])
interviewer_router = APIRouter(prefix="/interviewers", tags=["interviewers"])


# ---------- interviewers ----------

class InterviewerIn(BaseModel):
    name: str
    email: str


@interviewer_router.post("", status_code=201)
def create_interviewer(payload: InterviewerIn, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(Interviewer).where(Interviewer.email == payload.email))
    if existing:
        return {"id": str(existing.id), "name": existing.name, "email": existing.email}
    itv = Interviewer(name=payload.name, email=payload.email)
    db.add(itv)
    db.commit()
    return {"id": str(itv.id), "name": itv.name, "email": itv.email}


@interviewer_router.get("")
def list_interviewers(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Interviewer).order_by(Interviewer.name)).all()
    return [{"id": str(r.id), "name": r.name, "email": r.email} for r in rows]


# ---------- slot grid ----------

class GenerateSlotsIn(BaseModel):
    start_date: datetime.date
    end_date: datetime.date          # 含当天
    start_hour: int = 9              # 工作时间起(MYT)
    end_hour: int = 18               # 工作时间止(不含)
    skip_weekends: bool = True


@router.post("/generate", status_code=201)
def generate_slots(payload: GenerateSlotsIn, db: Session = Depends(get_db)) -> dict:
    """按固定时长生成 empty 时段网格;已存在的(同日期同起点)跳过。"""
    if payload.end_date < payload.start_date:
        raise HTTPException(422, "end_date must be >= start_date")
    if (payload.end_date - payload.start_date).days > 31:
        raise HTTPException(422, "range too large (max 31 days)")
    if not (0 <= payload.start_hour < payload.end_hour <= 24):
        raise HTTPException(422, "invalid hour range")

    duration_min = get_setting_int(db, "slot_duration_minutes", 60)
    existing = {
        (r.slot_date, r.start_time)
        for r in db.scalars(
            select(Slot).where(
                Slot.slot_date.between(payload.start_date, payload.end_date)
            )
        )
    }
    created = 0
    day = payload.start_date
    while day <= payload.end_date:
        if payload.skip_weekends and day.weekday() >= 5:
            day += datetime.timedelta(days=1)
            continue
        cursor = datetime.datetime.combine(day, datetime.time(payload.start_hour, 0))
        day_end = datetime.datetime.combine(day, datetime.time(payload.end_hour - 1, 59))
        while cursor + datetime.timedelta(minutes=duration_min) <= day_end + datetime.timedelta(minutes=1):
            start_t = cursor.time()
            if (day, start_t) not in existing:
                end_dt = cursor + datetime.timedelta(minutes=duration_min)
                db.add(Slot(slot_date=day, start_time=start_t, end_time=end_dt.time()))
                created += 1
            cursor += datetime.timedelta(minutes=duration_min)
        day += datetime.timedelta(days=1)
    db.commit()
    return {"created": created}


@router.get("")
def list_slots(
    start_date: datetime.date,
    end_date: datetime.date,
    db: Session = Depends(get_db),
) -> list[dict]:
    slots = db.scalars(
        select(Slot)
        .where(Slot.slot_date.between(start_date, end_date))
        .order_by(Slot.slot_date, Slot.start_time)
    ).all()
    slot_ids = [s.id for s in slots]
    claims: dict[uuid.UUID, list[dict]] = {}
    if slot_ids:
        rows = db.execute(
            select(SlotInterviewer.slot_id, Interviewer.id, Interviewer.name)
            .join(Interviewer, Interviewer.id == SlotInterviewer.interviewer_id)
            .where(SlotInterviewer.slot_id.in_(slot_ids))
        ).all()
        for slot_id, itv_id, itv_name in rows:
            claims.setdefault(slot_id, []).append({"id": str(itv_id), "name": itv_name})
    return [
        {
            "id": str(s.id),
            "date": s.slot_date.isoformat(),
            "start": s.start_time.strftime("%H:%M"),
            "end": s.end_time.strftime("%H:%M"),
            "status": s.status,
            "interviewers": claims.get(s.id, []),
        }
        for s in slots
    ]


# ---------- claim / withdraw ----------

class ClaimIn(BaseModel):
    interviewer_id: uuid.UUID


@router.post("/{slot_id}/claim")
def claim_slot(slot_id: uuid.UUID, payload: ClaimIn, db: Session = Depends(get_db)) -> dict:
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise HTTPException(404, "slot not found")
    if db.get(Interviewer, payload.interviewer_id) is None:
        raise HTTPException(404, "interviewer not found")
    if db.get(SlotInterviewer, (slot_id, payload.interviewer_id)):
        raise HTTPException(409, "already claimed by this interviewer")
    db.add(SlotInterviewer(slot_id=slot_id, interviewer_id=payload.interviewer_id))
    try:
        db.flush()  # 触发 panel 上限 trigger
    except DBAPIError as e:
        db.rollback()
        raise HTTPException(409, f"claim rejected: {e.orig}") from e
    recompute_unbooked_status(db, slot)
    db.commit()
    return {"slot_id": str(slot_id), "status": slot.status}


@router.delete("/{slot_id}/claim/{interviewer_id}")
def withdraw_claim(
    slot_id: uuid.UUID, interviewer_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise HTTPException(404, "slot not found")
    claim = db.get(SlotInterviewer, (slot_id, interviewer_id))
    if claim is None:
        raise HTTPException(404, "claim not found")
    db.delete(claim)
    try:
        db.flush()  # 触发 booked 保底 trigger(最后一位不能退)
    except DBAPIError as e:
        db.rollback()
        raise HTTPException(409, f"withdraw rejected: {e.orig}") from e
    recompute_unbooked_status(db, slot)
    db.commit()
    return {"slot_id": str(slot_id), "status": slot.status}
