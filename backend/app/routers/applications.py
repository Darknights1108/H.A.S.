"""申请与审查 API。

公开:GET /jobs(开放职位)、POST /applications(提交申请,提交即自动打分分流)
管理:GET /applications(审查队列)、POST /applications/{id}/approve(草拟邀请信)、
      POST /applications/{id}/reject(人工淘汰)

分流规则:High/Medium → shortlisted(等 admin 审查,不自动发信);
          Low → rejected(low_band)+ 婉拒信草稿(仍留在 talent bank,需候选人同意)。
"""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..config import settings
from ..database import get_db
from ..models import Application, Candidate, Interview, Job, Score, Slot, UserSession
from ..services.scheduling import draft_email
from ..services.scoring import score_application

router = APIRouter(tags=["applications"])


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(select(Job).where(Job.is_open).order_by(Job.created_at)).all()
    return [{"id": str(j.id), "title": j.title, "description": j.description} for j in jobs]


# ---------- public submission ----------

class ApplicationIn(BaseModel):
    job_id: uuid.UUID
    name: str = Field(min_length=1)
    email: EmailStr
    phone: str | None = None
    cgpa: float = Field(ge=0, le=4)
    degree_field: str
    is_fulltime: bool
    prog_langs: list[str] = []
    has_sql: bool = False
    has_ai_study: bool = False
    eca: str | None = None
    consent_talent_bank: bool = False


@router.post("/applications", status_code=201)
def submit_application(payload: ApplicationIn, db: Session = Depends(get_db)) -> dict:
    job = db.get(Job, payload.job_id)
    if job is None or not job.is_open:
        raise HTTPException(404, "job not found or closed")

    candidate = db.scalar(select(Candidate).where(Candidate.email == payload.email))
    if candidate is None:
        candidate = Candidate(
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            consent_talent_bank=payload.consent_talent_bank,
        )
        db.add(candidate)
        db.flush()
    else:
        candidate.consent_talent_bank = candidate.consent_talent_bank or payload.consent_talent_bank

    dup = db.scalar(
        select(Application).where(
            Application.candidate_id == candidate.id, Application.job_id == job.id
        )
    )
    if dup is not None:
        raise HTTPException(409, "you have already applied to this job")

    app_ = Application(
        candidate_id=candidate.id,
        job_id=job.id,
        cgpa=payload.cgpa,
        degree_field=payload.degree_field,
        is_fulltime=payload.is_fulltime,
        prog_langs=payload.prog_langs,
        has_sql=payload.has_sql,
        has_ai_study=payload.has_ai_study,
        eca=payload.eca,
        form_data=payload.model_dump(mode="json"),
        status="applied",
    )
    db.add(app_)
    db.flush()

    # 提交即打分分流
    score = score_application(db, app_)
    if score.band == "low":
        app_.status = "rejected"
        app_.rejected_reason = "low_band"
        draft_email(
            db, app_, "reject",
            f"Your application — {job.title}",
            (
                f"Hi {candidate.name},\n\n"
                f"Thank you for applying to {job.title}. After careful review, we will "
                f"not be moving forward with your application at this time.\n\n"
                + (
                    "Your profile has been kept in our talent bank and we may reach "
                    "out when a suitable opportunity opens.\n\n"
                    if candidate.consent_talent_bank
                    else ""
                )
                + "We wish you all the best.\n"
            ),
        )
    else:
        app_.status = "shortlisted"
        app_.shortlisted_at = datetime.datetime.now(datetime.timezone.utc)

    db.commit()
    # 对候选人只返回"已收到",不暴露打分结果
    return {"application_id": str(app_.id), "message": "Application received. We will be in touch."}


# ---------- admin review ----------

@router.get("/applications")
def list_applications(db: Session = Depends(get_db),
                      _admin: UserSession = Depends(require_admin)) -> list[dict]:
    rows = db.execute(
        select(Application, Candidate, Score, Job)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Job, Job.id == Application.job_id)
        .outerjoin(Score, Score.application_id == Application.id)
        .order_by(Application.submitted_at.desc())
    ).all()
    # 各申请当前排定的面试(用于显示时间 + Pass/Fail 操作)
    itv_map = {
        i.application_id: (i, sl)
        for i, sl in db.execute(
            select(Interview, Slot)
            .join(Slot, Slot.id == Interview.slot_id)
            .where(Interview.status == "scheduled")
        )
    }
    return [
        {
            "id": str(a.id),
            "candidate": {"name": c.name, "email": c.email},
            "job_title": j.title,
            "cgpa": float(a.cgpa) if a.cgpa is not None else None,
            "degree_field": a.degree_field,
            "prog_langs": a.prog_langs,
            "status": a.status,
            "rejected_reason": a.rejected_reason,
            "shortlisted_at": a.shortlisted_at.isoformat() if a.shortlisted_at else None,
            "band": s.band if s else None,
            "total_score": float(s.total_score) if s and s.total_score is not None else None,
            "reasoning": s.reasoning if s else None,
            "booking_url": f"{settings.frontend_base_url}/booking/{a.booking_token}",
            "submitted_at": a.submitted_at.isoformat(),
            "interview": (
                {
                    "date": itv_map[a.id][1].slot_date.isoformat(),
                    "start": itv_map[a.id][1].start_time.strftime("%H:%M"),
                    "end": itv_map[a.id][1].end_time.strftime("%H:%M"),
                    "meeting_link": itv_map[a.id][0].meeting_link,
                }
                if a.id in itv_map
                else None
            ),
        }
        for a, c, s, j in rows
    ]


@router.post("/applications/{application_id}/approve")
def approve_application(application_id: uuid.UUID, db: Session = Depends(get_db),
                        _admin: UserSession = Depends(require_admin)) -> dict:
    app_ = db.get(Application, application_id)
    if app_ is None:
        raise HTTPException(404, "application not found")
    if app_.status != "shortlisted":
        raise HTTPException(409, f"application not in shortlist ({app_.status})")
    candidate = db.get(Candidate, app_.candidate_id)
    job = db.get(Job, app_.job_id)
    booking_url = f"{settings.frontend_base_url}/booking/{app_.booking_token}"
    email = draft_email(
        db, app_, "invite",
        f"Interview invitation — {job.title}",
        (
            f"Hi {candidate.name},\n\n"
            f"Congratulations! You have been shortlisted for {job.title}.\n\n"
            f"Please pick an interview time that suits you using your personal "
            f"booking link:\n{booking_url}\n\n"
            f"All interviews are conducted online (times in MYT, UTC+08:00).\n"
        ),
    )
    db.commit()
    return {"application_id": str(app_.id), "invite_email_id": str(email.id), "booking_url": booking_url}


class OutcomeIn(BaseModel):
    result: str  # passed | failed


@router.post("/applications/{application_id}/outcome")
def record_outcome(
    application_id: uuid.UUID, payload: OutcomeIn, db: Session = Depends(get_db),
    _admin: UserSession = Depends(require_admin),
) -> dict:
    """面试结果:passed → offer 信草稿;failed → 婉拒信草稿 + talent bank。"""
    if payload.result not in ("passed", "failed"):
        raise HTTPException(422, "result must be 'passed' or 'failed'")
    app_ = db.get(Application, application_id)
    if app_ is None:
        raise HTTPException(404, "application not found")
    interview = db.scalar(
        select(Interview).where(
            Interview.application_id == application_id,
            Interview.status == "scheduled",
        )
    )
    if interview is None:
        raise HTTPException(409, "no scheduled interview for this application")
    candidate = db.get(Candidate, app_.candidate_id)
    job = db.get(Job, app_.job_id)

    interview.status = payload.result
    if payload.result == "passed":
        app_.status = "passed"
        email = draft_email(
            db, app_, "offer",
            f"Congratulations — {job.title}",
            (
                f"Hi {candidate.name},\n\n"
                f"Congratulations! We are pleased to inform you that you have "
                f"passed the interview for {job.title}.\n\n"
                f"Our team will follow up shortly with the offer details and "
                f"next steps (start date, documents, onboarding).\n\n"
                f"Welcome aboard!\n"
            ),
        )
    else:
        app_.status = "rejected"
        app_.rejected_reason = "interview_failed"
        email = draft_email(
            db, app_, "reject",
            f"Your interview result — {job.title}",
            (
                f"Hi {candidate.name},\n\n"
                f"Thank you for taking the time to interview for {job.title}. "
                f"After careful consideration, we will not be moving forward "
                f"with your application.\n\n"
                + (
                    "Your profile remains in our talent bank and we may reach "
                    "out when a suitable opportunity opens.\n\n"
                    if candidate.consent_talent_bank
                    else ""
                )
                + "We wish you all the best in your career.\n"
            ),
        )
    db.commit()
    return {
        "application_id": str(app_.id),
        "status": app_.status,
        "interview_status": interview.status,
        "email_draft_id": str(email.id),
    }


class RejectIn(BaseModel):
    reason: str = "manual"


@router.post("/applications/{application_id}/reject")
def reject_application(
    application_id: uuid.UUID, payload: RejectIn, db: Session = Depends(get_db),
    _admin: UserSession = Depends(require_admin),
) -> dict:
    app_ = db.get(Application, application_id)
    if app_ is None:
        raise HTTPException(404, "application not found")
    if app_.status in ("rejected", "passed"):
        raise HTTPException(409, f"application already finalised ({app_.status})")
    candidate = db.get(Candidate, app_.candidate_id)
    job = db.get(Job, app_.job_id)
    app_.status = "rejected"
    app_.rejected_reason = payload.reason
    draft_email(
        db, app_, "reject",
        f"Your application — {job.title}",
        (
            f"Hi {candidate.name},\n\n"
            f"Thank you for your interest in {job.title}. After careful review, we "
            f"will not be moving forward with your application.\n\n"
            f"We wish you all the best.\n"
        ),
    )
    db.commit()
    return {"application_id": str(app_.id), "status": app_.status}
