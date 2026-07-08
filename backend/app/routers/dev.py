"""Dev helper endpoints — local/demo only; remove or gate before production."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Candidate, Interviewer, Job

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/seed")
def seed_demo(db: Session = Depends(get_db)) -> dict:
    """Seed demo data: a job + a shortlisted candidate + two interviewers. Idempotent."""
    job = db.scalar(select(Job).where(Job.title == "RISE@MCMC Internship (Demo)"))
    if job is None:
        job = Job(
            title="RISE@MCMC Internship (Demo)",
            description="AI & digital intelligence internship — demo job",
            requirements={
                "knockout": {
                    "min_cgpa": 3.20,
                    "fields": ["CS", "SE", "IS", "IT", "Data Science"],
                    "require_fulltime": True,
                    "langs_any": ["Python", "PHP"],
                    "require_sql": True,
                },
                "bonus": {"ai_study": 10, "eca": 8, "extra_lang": 5},
            },
        )
        db.add(job)
        db.flush()

    cand = db.scalar(select(Candidate).where(Candidate.email == "demo.candidate@example.com"))
    if cand is None:
        cand = Candidate(
            name="Ang Zhen Loong",
            email="demo.candidate@example.com",
            phone="0162064912",
            consent_talent_bank=True,
        )
        db.add(cand)
        db.flush()

    app_ = db.scalar(
        select(Application).where(
            Application.candidate_id == cand.id, Application.job_id == job.id
        )
    )
    if app_ is None:
        app_ = Application(
            candidate_id=cand.id,
            job_id=job.id,
            cgpa=3.65,
            degree_field="CS",
            is_fulltime=True,
            prog_langs=["Python", "SQL"],
            has_sql=True,
            has_ai_study=True,
            status="shortlisted",
        )
        db.add(app_)
        db.flush()

    interviewers = []
    for name, email in [
        ("Michael Costevec", "michael@example.com"),
        ("Siti Rahman", "siti@example.com"),
    ]:
        itv = db.scalar(select(Interviewer).where(Interviewer.email == email))
        if itv is None:
            itv = Interviewer(name=name, email=email)
            db.add(itv)
            db.flush()
        interviewers.append(itv)

    db.commit()
    return {
        "job_id": str(job.id),
        "candidate_id": str(cand.id),
        "application_id": str(app_.id),
        "booking_token": str(app_.booking_token),
        "booking_url": f"http://localhost:3000/booking/{app_.booking_token}",
        "interviewer_ids": [str(i.id) for i in interviewers],
    }
