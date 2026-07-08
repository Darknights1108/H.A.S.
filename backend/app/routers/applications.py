"""Applications & review API.

Public: GET /jobs (open positions), POST /applications (submit an application)
Admin: GET /applications (review queue), POST /applications/{id}/approve (draft the invite),
       POST /applications/{id}/reject (manual rejection)

Routing: High/Medium -> shortlisted (awaits admin review; nothing auto-sent);
          Low -> rejected (low_band) + rejection letter draft (kept in the talent bank with consent).
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
from ..models import (Application, Candidate, EmailLog, Interview, Interviewer, Job,
                      Score, Slot, SlotInterviewer, UserSession)
from ..services import llm
from ..services.mailer import try_send_draft
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


# ---------- resume skill suggestion (pre-submit; extracts skill chips from the resume) ----------

@router.post("/resume/skill-suggest")
def suggest_skills(resume: UploadFile = File(...)) -> dict:
    """Instantly extract a skill list from the uploaded resume for the form's suggestion chips."""
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


# ---------- scoring helpers ----------

KNOWN_LANGS = ["Python", "PHP", "Java", "JavaScript", "TypeScript", "C++", "C#", "C",
               "Go", "Golang", "Ruby", "Swift", "Kotlin", "R", "Rust", "Scala", "MATLAB"]
AI_KEYWORDS = ["ai", "machine learning", "deep learning", "nlp", "llm", "neural",
               "computer vision", "scikit", "tensorflow", "pytorch", "langchain",
               "rag", "genai", "generative", "data science"]


def _derive_scoring_flags(skills: list[str]) -> tuple[list[str], bool, bool]:
    """Derive scoring inputs from the skill list: programming languages / SQL / AI."""
    low = [x.lower() for x in skills]
    langs: list[str] = []
    for lang in KNOWN_LANGS:
        ll = lang.lower()
        if any(l == ll or ll in l.split() for l in low):
            canonical = "Go" if lang == "Golang" else lang
            if canonical not in langs:
                langs.append(canonical)
    has_sql = any("sql" in l for l in low)
    has_ai = any(k in l for l in low for k in AI_KEYWORDS)
    return langs, has_sql, has_ai


def _score_and_route(db: Session, app_: Application, candidate: Candidate, job: Job) -> None:
    """Score and route: Low -> reject + letter; otherwise shortlist."""
    score = score_application(db, app_)
    if score.band == "low":
        app_.status = "rejected"
        app_.rejected_reason = "low_band"
        subject, body = rejection_email(db, candidate, job, after_interview=False)
        draft_email(db, app_, "reject", subject, body)
    else:
        app_.status = "shortlisted"
        app_.shortlisted_at = datetime.datetime.now(datetime.timezone.utc)


# ---------- public submission (multipart: form fields + optional resume file) ----------

class ApplicationIn(BaseModel):
    """Multipart fields are parsed into this model before the original logic runs."""

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
    # Optional extra info (stored in form_data only; not scored)
    education_level: str | None = Form(None),
    institution: str | None = Form(None),
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

    # Validate the resume first (type/size); store it after the application row exists
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
            "education_level": education_level,
            "institution": institution,
            "preferred_start_date": preferred_start_date,
            "salary_expectation": salary_expectation,
            "heard_about_us": heard_about_us,
        },
        status="applied",
    )
    db.add(app_)
    db.flush()

    # Store the resume in object storage (never swallow storage failures: the candidate should retry, not lose the file silently)
    if resume_data is not None:
        key = f"{app_.id}{resume_ext}"
        try:
            put_resume(key, resume_data, resume_ext)
        except Exception as e:
            raise HTTPException(503, f"resume storage unavailable, please retry: {e}") from e
        app_.resume_file_url = key
        app_.resume_parse_status = "pending"

    # Scoring is deferred until Skill Assessment completes (languages/SQL/AI derived from the skill list)
    db.commit()
    if resume_data is not None:
        parse_resume_async(app_.id)  # background LLM parse; never blocks submission
    return {
        "application_id": str(app_.id),
        "skill_token": str(app_.booking_token),
        "message": "Application received. One more step: tell us your skills.",
    }


# ---------- skill assessment (step 2 after submission; public, token-based) ----------

@router.get("/skill-assessment/{token}")
def get_skill_assessment(token: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    app_ = db.scalar(select(Application).where(Application.booking_token == token))
    if app_ is None:
        raise HTTPException(404, "not found")
    job = db.get(Job, app_.job_id)
    criteria = (job.requirements or {}).get("criteria") or {}
    job_skills = list((criteria.get("must_have") or [])) + list((criteria.get("nice_to_have") or []))
    resume_skills: list[str] = []
    if app_.resume_parse_status == "done" and app_.resume_parsed:
        resume_skills = list(app_.resume_parsed.get("programming_languages") or []) +                         list(app_.resume_parsed.get("other_skills") or [])
    return {
        "job_title": job.title,
        "done": app_.status != "applied",
        "current_skills": (app_.form_data or {}).get("skills") or [],
        "job_skills": job_skills[:20],
        "resume_skills": resume_skills[:30],
        "resume_parse_status": app_.resume_parse_status,
    }


class SkillsIn(BaseModel):
    skills: list[str] = []


@router.post("/skill-assessment/{token}")
def submit_skill_assessment(token: uuid.UUID, payload: SkillsIn,
                            db: Session = Depends(get_db)) -> dict:
    """Complete the skill assessment: store skills -> derive scoring inputs -> score and route. One submission per application."""
    app_ = db.scalar(select(Application).where(Application.booking_token == token))
    if app_ is None:
        raise HTTPException(404, "not found")
    if app_.status != "applied":
        raise HTTPException(409, "skill assessment already completed")

    skills = [str(x).strip()[:60] for x in payload.skills if str(x).strip()][:50]
    langs, has_sql, has_ai = _derive_scoring_flags(skills)
    app_.form_data = {**(app_.form_data or {}), "skills": skills}
    app_.prog_langs = langs
    app_.has_sql = has_sql
    app_.has_ai_study = has_ai

    candidate = db.get(Candidate, app_.candidate_id)
    job = db.get(Job, app_.job_id)
    _score_and_route(db, app_, candidate, job)
    db.commit()
    return {"message": "Application complete. We will be in touch soon."}


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
    # Invite status (none/draft/sent) — drives review-page display and buttons
    invite_map: dict = {}
    for app_id, status in db.execute(
        select(EmailLog.application_id, EmailLog.status).where(EmailLog.type == "invite")
    ):
        if invite_map.get(app_id) != "sent":
            invite_map[app_id] = status
    # Each application's currently scheduled interview (for display + outcome actions)
    itv_map = {
        i.application_id: (i, sl)
        for i, sl in db.execute(
            select(Interview, Slot)
            .join(Slot, Slot.id == Interview.slot_id)
            .where(Interview.status == "scheduled")
        )
    }
    # interview panel names
    slot_ids = [sl.id for _, sl in itv_map.values()]
    panel_map: dict = {}
    if slot_ids:
        for sid, name in db.execute(
            select(SlotInterviewer.slot_id, Interviewer.name)
            .join(Interviewer, Interviewer.id == SlotInterviewer.interviewer_id)
            .where(SlotInterviewer.slot_id.in_(slot_ids))
        ):
            panel_map.setdefault(sid, []).append(name)
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
            "invite_status": invite_map.get(a.id, "none"),
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
                    "panel": panel_map.get(itv_map[a.id][1].id, []),
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
    booking_url = f"{settings.frontend_base_url}/booking/{app_.booking_token}"
    # Idempotent: never draft a duplicate invite
    existing = db.scalar(
        select(EmailLog).where(
            EmailLog.application_id == app_.id, EmailLog.type == "invite"
        ).order_by(EmailLog.created_at.desc())
    )
    if existing is not None:
        return {
            "application_id": str(app_.id),
            "invite_email_id": str(existing.id),
            "booking_url": booking_url,
            "already": existing.status,  # draft | sent
        }
    candidate = db.get(Candidate, app_.candidate_id)
    job = db.get(Job, app_.job_id)
    subject, body = invite_email(db, candidate, job, booking_url)
    email = draft_email(db, app_, "invite", subject, body)
    db.commit()
    return {"application_id": str(app_.id), "invite_email_id": str(email.id), "booking_url": booking_url}


@router.get("/resumes")
def list_resumes(db: Session = Depends(get_db),
                 _staff: UserSession = Depends(get_session)) -> list[dict]:
    """All uploaded resumes (viewable/downloadable by admin and interviewers)."""
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
    """Resume file (staff: admin + interviewer). inline=true serves it for in-browser preview."""
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
    """Interview outcome: passed -> offer letter; failed -> rejection letter + talent bank."""
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
    offer_sent = False
    if payload.result == "passed":
        app_.status = "passed"
        subject, body = offer_email(db, candidate, job)
        email = draft_email(db, app_, "offer", subject, body)
        db.flush()
        offer_sent = try_send_draft(db, email)  # Sends on Accept; failure keeps the draft for a manual send
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
        "offer_sent": offer_sent,
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
