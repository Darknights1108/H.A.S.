"""申请与审查 API。

公开:GET /jobs(开放职位)、POST /applications(提交申请,提交即自动打分分流)
管理:GET /applications(审查队列)、POST /applications/{id}/approve(草拟邀请信)、
      POST /applications/{id}/reject(人工淘汰)

分流规则:High/Medium → shortlisted(等 admin 审查,不自动发信);
          Low → rejected(low_band)+ 婉拒信草稿(仍留在 talent bank,需候选人同意)。
"""

import datetime
import io
import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_session, require_admin
from ..config import settings
from ..database import get_db
from ..models import Application, Candidate, Interview, Job, Score, Slot, UserSession
from ..services import llm
from ..services.resume import ALLOWED_EXTS, MAX_SIZE, extract_text, parse_resume_async
from ..services.scheduling import draft_email
from ..services.scoring import score_application
from ..services.storage import CONTENT_TYPES, get_resume, put_resume
from ..services.templates import invite_email, offer_email, rejection_email

router = APIRouter(tags=["applications"])


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(select(Job).where(Job.is_open).order_by(Job.created_at)).all()
    return [{"id": str(j.id), "title": j.title, "description": j.description} for j in jobs]


# ---------- resume skill suggestion(提交前调用,从简历提取技能 chips)----------

@router.post("/resume/skill-suggest")
def suggest_skills(resume: UploadFile = File(...)) -> dict:
    """从上传的简历即时提取技能列表,供申请表 Skills 区显示建议 chips。"""
    if llm.provider() is None:
        raise HTTPException(503, "skill suggestion unavailable (no LLM key)")
    if not resume.filename or "." not in resume.filename:
        raise HTTPException(422, "invalid file")
    ext = "." + resume.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(422, f"resume must be one of {sorted(ALLOWED_EXTS)}")
    data = resume.file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(422, "resume too large (max 5MB)")
    try:
        text = extract_text(data, ext)
        parsed, model = llm.tool_call(
            prompt=(
                "Extract ALL skills from this resume: technical skills, tools, "
                "frameworks, languages (programming and spoken), and soft skills. "
                "Short labels (1-3 words each), no duplicates.\n\n--- RESUME ---\n" + text
            ),
            tool_name="submit_skills",
            description="Submit the list of skills found in the resume.",
            schema={
                "type": "object",
                "properties": {"skills": {"type": "array", "items": {"type": "string"}}},
                "required": ["skills"],
            },
            max_tokens=600,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"skill extraction failed: {e}") from e
    seen: set[str] = set()
    skills: list[str] = []
    for x in parsed.get("skills", []):
        label = str(x).strip()
        if label and len(label) <= 40 and label.lower() not in seen:
            seen.add(label.lower())
            skills.append(label)
    return {"skills": skills[:30], "model": model}


# ---------- public submission(multipart:表单字段 + 可选简历文件)----------

class ApplicationIn(BaseModel):
    """multipart 字段先解析成本模型再走原有逻辑。"""

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
def submit_application(
    job_id: uuid.UUID = Form(...),
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: str | None = Form(None),
    cgpa: float = Form(..., ge=0, le=4),
    degree_field: str = Form(...),
    is_fulltime: bool = Form(...),
    prog_langs: str = Form("[]"),          # JSON array string
    has_sql: bool = Form(False),
    has_ai_study: bool = Form(False),
    eca: str | None = Form(None),
    consent_talent_bank: bool = Form(False),
    # 可选补充信息(仅存 form_data,不参与打分)
    skills: str = Form("[]"),               # JSON array string
    preferred_start_date: str | None = Form(None),
    salary_expectation: str | None = Form(None),
    heard_about_us: str | None = Form(None),
    resume: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> dict:
    try:
        langs = json.loads(prog_langs)
        assert isinstance(langs, list)
        langs = [str(x) for x in langs]
    except (ValueError, AssertionError):
        raise HTTPException(422, "prog_langs must be a JSON array of strings")
    try:
        skill_list = json.loads(skills)
        assert isinstance(skill_list, list)
        skill_list = [str(x).strip()[:40] for x in skill_list if str(x).strip()][:30]
    except (ValueError, AssertionError):
        raise HTTPException(422, "skills must be a JSON array of strings")

    payload = ApplicationIn(
        job_id=job_id, name=name, email=email, phone=phone or None, cgpa=cgpa,
        degree_field=degree_field, is_fulltime=is_fulltime, prog_langs=langs,
        has_sql=has_sql, has_ai_study=has_ai_study, eca=eca or None,
        consent_talent_bank=consent_talent_bank,
    )

    # 简历文件先校验(格式/大小),申请建好后再入库存储
    resume_data: bytes | None = None
    resume_ext = ""
    if resume is not None and resume.filename:
        resume_ext = "." + resume.filename.rsplit(".", 1)[-1].lower() if "." in resume.filename else ""
        if resume_ext not in ALLOWED_EXTS:
            raise HTTPException(422, f"resume must be one of {sorted(ALLOWED_EXTS)}")
        resume_data = resume.file.read()
        if len(resume_data) > MAX_SIZE:
            raise HTTPException(422, "resume too large (max 5MB)")

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
        form_data={
            **payload.model_dump(mode="json"),
            "skills": skill_list,
            "preferred_start_date": preferred_start_date,
            "salary_expectation": salary_expectation,
            "heard_about_us": heard_about_us,
        },
        status="applied",
    )
    db.add(app_)
    db.flush()

    # 简历入对象存储(存储故障不吞:候选人应重试,而不是简历悄悄丢失)
    if resume_data is not None:
        key = f"{app_.id}{resume_ext}"
        try:
            put_resume(key, resume_data, resume_ext)
        except Exception as e:
            raise HTTPException(503, f"resume storage unavailable, please retry: {e}") from e
        app_.resume_file_url = key
        app_.resume_parse_status = "pending"

    # 提交即打分分流(表单为主数据源,与简历解析解耦)
    score = score_application(db, app_)
    if score.band == "low":
        app_.status = "rejected"
        app_.rejected_reason = "low_band"
        subject, body = rejection_email(db, candidate, job, after_interview=False)
        draft_email(db, app_, "reject", subject, body)
    else:
        app_.status = "shortlisted"
        app_.shortlisted_at = datetime.datetime.now(datetime.timezone.utc)

    db.commit()
    if resume_data is not None:
        parse_resume_async(app_.id)  # 后台 LLM 解析,不阻塞提交
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
            "skills": (a.form_data or {}).get("skills") or [],
            "booking_url": f"{settings.frontend_base_url}/booking/{a.booking_token}",
            "submitted_at": a.submitted_at.isoformat(),
            "resume": {
                "uploaded": bool(a.resume_file_url),
                "status": a.resume_parse_status,
                "parsed": a.resume_parsed,
            },
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
    subject, body = invite_email(db, candidate, job, booking_url)
    email = draft_email(db, app_, "invite", subject, body)
    db.commit()
    return {"application_id": str(app_.id), "invite_email_id": str(email.id), "booking_url": booking_url}


@router.get("/resumes")
def list_resumes(db: Session = Depends(get_db),
                 _staff: UserSession = Depends(get_session)) -> list[dict]:
    """全部已上传简历(admin 与 interviewer 均可查看/下载)。"""
    rows = db.execute(
        select(Application, Candidate, Job)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Job, Job.id == Application.job_id)
        .where(Application.resume_file_url.isnot(None))
        .order_by(Application.submitted_at.desc())
    ).all()
    return [
        {
            "application_id": str(a.id),
            "candidate_name": c.name,
            "candidate_email": c.email,
            "job_title": j.title,
            "file_ext": a.resume_file_url.rsplit(".", 1)[-1].lower(),
            "parse_status": a.resume_parse_status,
            "application_status": a.status,
            "submitted_at": a.submitted_at.isoformat(),
        }
        for a, c, j in rows
    ]


@router.get("/applications/{application_id}/resume")
def download_resume(application_id: uuid.UUID, inline: bool = False,
                    db: Session = Depends(get_db),
                    _staff: UserSession = Depends(get_session)) -> StreamingResponse:
    """简历文件(staff:admin + interviewer)。inline=true 时浏览器内预览。"""
    app_ = db.get(Application, application_id)
    if app_ is None or not app_.resume_file_url:
        raise HTTPException(404, "no resume for this application")
    try:
        data = get_resume(app_.resume_file_url)
    except Exception as e:
        raise HTTPException(502, f"storage error: {e}") from e
    ext = "." + app_.resume_file_url.rsplit(".", 1)[-1].lower()
    disposition = "inline" if inline else "attachment"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=CONTENT_TYPES.get(ext, "application/octet-stream"),
        headers={"Content-Disposition": f'{disposition}; filename="resume{ext}"'},
    )


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
        subject, body = offer_email(db, candidate, job)
        email = draft_email(db, app_, "offer", subject, body)
    else:
        app_.status = "rejected"
        app_.rejected_reason = "interview_failed"
        subject, body = rejection_email(db, candidate, job, after_interview=True)
        email = draft_email(db, app_, "reject", subject, body)
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
    subject, body = rejection_email(db, candidate, job, after_interview=False)
    draft_email(db, app_, "reject", subject, body)
    db.commit()
    return {"application_id": str(app_.id), "status": app_.status}
