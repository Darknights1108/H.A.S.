"""排期 API:面试官管理、时段网格生成、认领/撤回。

认证:登录会话(cookie)。generate/面试官创建 = admin;认领/撤回 = 任何 staff,
非 admin 的身份强制取自会话邮箱(不能替别人认领);admin 需显式指定 interviewer_id。
"""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..auth import get_session, require_admin, resolve_interviewer
from ..database import get_db
from ..models import Candidate, Interviewer, Slot, SlotInterviewer, UserSession
from ..services.scheduling import get_setting_int, recompute_unbooked_status


def _acting_interviewer_id(
    db: Session, sess: UserSession, requested: uuid.UUID | None
) -> uuid.UUID:
    """确定操作身份:非 admin 强制为本人;admin 必须显式指定。"""
    if sess.role != "admin":
        return resolve_interviewer(db, sess.email).id
    if requested is None:
        raise HTTPException(422, "admin must specify interviewer_id")
    return requested

router = APIRouter(prefix="/slots", tags=["slots"])
interviewer_router = APIRouter(prefix="/interviewers", tags=["interviewers"])


# ---------- interviewers ----------

class InterviewerIn(BaseModel):
    name: str
    email: str


@interviewer_router.post("", status_code=201)
def create_interviewer(payload: InterviewerIn, db: Session = Depends(get_db),
                       _admin: UserSession = Depends(require_admin)) -> dict:
    existing = db.scalar(select(Interviewer).where(Interviewer.email == payload.email))
    if existing:
        return {"id": str(existing.id), "name": existing.name, "email": existing.email}
    itv = Interviewer(name=payload.name, email=payload.email)
    db.add(itv)
    db.commit()
    return {"id": str(itv.id), "name": itv.name, "email": itv.email}


@interviewer_router.get("")
def list_interviewers(db: Session = Depends(get_db),
                      _sess: UserSession = Depends(get_session)) -> list[dict]:
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
def generate_slots(payload: GenerateSlotsIn, db: Session = Depends(get_db),
                   _admin: UserSession = Depends(require_admin)) -> dict:
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
    _sess: UserSession = Depends(get_session),
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
    cand_names: dict[uuid.UUID, str] = {}
    cand_ids = [s.candidate_id for s in slots if s.candidate_id]
    if cand_ids:
        cand_names = {
            c.id: c.name
            for c in db.scalars(select(Candidate).where(Candidate.id.in_(cand_ids)))
        }
    return [
        {
            "id": str(s.id),
            "date": s.slot_date.isoformat(),
            "start": s.start_time.strftime("%H:%M"),
            "end": s.end_time.strftime("%H:%M"),
            "status": s.status,
            "interviewers": claims.get(s.id, []),
            "candidate_name": cand_names.get(s.candidate_id) if s.candidate_id else None,
        }
        for s in slots
    ]


# ---------- bulk claim / withdraw ----------

class BulkClaimIn(BaseModel):
    interviewer_id: uuid.UUID | None = None  # 非 admin 忽略此字段,身份取会话
    start_date: datetime.date
    end_date: datetime.date


@router.post("/claim-bulk")
def claim_bulk(payload: BulkClaimIn, db: Session = Depends(get_db),
               sess: UserSession = Depends(get_session)) -> dict:
    """认领范围内所有可认领的时段(跳过:已被订、已认领过、panel 已满)。"""
    interviewer_id = _acting_interviewer_id(db, sess, payload.interviewer_id)
    if db.get(Interviewer, interviewer_id) is None:
        raise HTTPException(404, "interviewer not found")
    cap = get_setting_int(db, "panel_max_interviewers", 5)
    slots = db.scalars(
        select(Slot)
        .where(Slot.slot_date.between(payload.start_date, payload.end_date))
        .with_for_update()
    ).all()
    counts = dict(
        db.execute(
            select(SlotInterviewer.slot_id, func.count())
            .where(SlotInterviewer.slot_id.in_([s.id for s in slots] or [None]))
            .group_by(SlotInterviewer.slot_id)
        ).all()
    )
    mine = set(
        db.scalars(
            select(SlotInterviewer.slot_id).where(
                SlotInterviewer.interviewer_id == interviewer_id
            )
        )
    )
    claimed, skipped = 0, 0
    for slot in slots:
        if slot.status == "booked" or slot.id in mine or counts.get(slot.id, 0) >= cap:
            skipped += 1
            continue
        db.add(SlotInterviewer(slot_id=slot.id, interviewer_id=interviewer_id))
        slot.status = "open"
        claimed += 1
    db.commit()
    return {"claimed": claimed, "skipped": skipped}


@router.post("/withdraw-bulk")
def withdraw_bulk(payload: BulkClaimIn, db: Session = Depends(get_db),
                  sess: UserSession = Depends(get_session)) -> dict:
    """撤回范围内该面试官的所有认领(跳过:已被订且自己是最后一位面试官的时段)。"""
    interviewer_id = _acting_interviewer_id(db, sess, payload.interviewer_id)
    rows = db.execute(
        select(SlotInterviewer, Slot)
        .join(Slot, Slot.id == SlotInterviewer.slot_id)
        .where(
            SlotInterviewer.interviewer_id == interviewer_id,
            Slot.slot_date.between(payload.start_date, payload.end_date),
        )
        .with_for_update()
    ).all()
    slot_ids = [s.id for _, s in rows]
    counts = dict(
        db.execute(
            select(SlotInterviewer.slot_id, func.count())
            .where(SlotInterviewer.slot_id.in_(slot_ids or [None]))
            .group_by(SlotInterviewer.slot_id)
        ).all()
    )
    withdrawn, skipped = 0, 0
    for claim, slot in rows:
        if slot.status == "booked" and counts.get(slot.id, 0) <= 1:
            skipped += 1  # booked 时段不能退到 0 面试官
            continue
        db.delete(claim)
        counts[slot.id] = counts.get(slot.id, 1) - 1
        if slot.status != "booked":
            slot.status = "open" if counts[slot.id] > 0 else "empty"
        withdrawn += 1
    db.commit()
    return {"withdrawn": withdrawn, "skipped": skipped}


# ---------- claim / withdraw ----------

class ClaimIn(BaseModel):
    interviewer_id: uuid.UUID | None = None  # 非 admin 忽略此字段,身份取会话


@router.post("/{slot_id}/claim")
def claim_slot(slot_id: uuid.UUID, payload: ClaimIn, db: Session = Depends(get_db),
               sess: UserSession = Depends(get_session)) -> dict:
    interviewer_id = _acting_interviewer_id(db, sess, payload.interviewer_id)
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise HTTPException(404, "slot not found")
    if db.get(Interviewer, interviewer_id) is None:
        raise HTTPException(404, "interviewer not found")
    if db.get(SlotInterviewer, (slot_id, interviewer_id)):
        raise HTTPException(409, "already claimed by this interviewer")
    db.add(SlotInterviewer(slot_id=slot_id, interviewer_id=interviewer_id))
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
    slot_id: uuid.UUID, interviewer_id: uuid.UUID, db: Session = Depends(get_db),
    sess: UserSession = Depends(get_session),
) -> dict:
    # 非 admin 只能撤自己的认领
    if sess.role != "admin":
        own = resolve_interviewer(db, sess.email).id
        if interviewer_id != own:
            raise HTTPException(403, "can only withdraw your own claims")
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
