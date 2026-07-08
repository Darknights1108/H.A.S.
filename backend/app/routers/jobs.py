"""Jobs management API (admin).

- POST /jobs            create a job (with structured screening rules)
- PATCH /jobs/{id}      update rules / open-close the job
- GET  /jobs/all        admin list (incl. closed jobs + rules)
- POST /jobs/parse      * chat box: hand the raw JD to the LLM, get a screening-rule draft
                          (needs an LLM key; returns 503 without one and the frontend falls back to manual entry)

The scoring engine executes job.requirements dynamically; new jobs take effect immediately, no code changes.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy import func

from ..auth import require_admin
from ..database import get_db
from ..models import Application, Job, UserSession
from ..services import llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])

# Parse target vocabulary: must stay in sync with the checks in services/scoring.py
PARSE_TOOL = {
    "name": "submit_screening_rules",
    "description": "Submit the screening rules extracted from the job description.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short job title"},
            "description": {"type": "string", "description": "1-3 sentence summary of the role"},
            "knockout": {
                "type": "object",
                "description": "Hard requirements. OMIT any key the JD does not require.",
                "properties": {
                    "min_cgpa": {"type": "number", "description": "Minimum CGPA on a 4.00 scale"},
                    "fields": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Accepted degree fields, full names, e.g. Computer Science, "
                                       "Software Engineering, Data Science, Engineering, Business, "
                                       "Accounting, Finance, Marketing. OMIT if the JD accepts any field.",
                    },
                    "require_fulltime": {"type": "boolean"},
                    "langs_any": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Candidate must know at least ONE of these programming languages",
                    },
                    "require_sql": {"type": "boolean"},
                },
            },
            "bonus": {
                "type": "object",
                "description": "Bonus points for nice-to-have criteria (typical 5-10 each).",
                "properties": {
                    "ai_study": {"type": "number", "description": "Points if candidate studied AI"},
                    "eca": {"type": "number", "description": "Points for extra-curricular activities"},
                    "extra_lang": {"type": "number", "description": "Points for knowing >1 language"},
                },
            },
            "high_min_bonus": {
                "type": "number",
                "description": "Minimum total bonus points for High band (default 15)",
            },
            "criteria": {
                "type": "object",
                "description": "The digested screening profile of this JD. Resumes will be "
                               "evaluated against these lists, so make them complete and specific.",
                "properties": {
                    "summary": {"type": "string",
                                "description": "2-3 sentences: what this role actually does and needs"},
                    "must_have": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Hard requirements distilled from the JD as short specific "
                                       "phrases, e.g. 'Java + Flink SQL hands-on experience'",
                    },
                    "nice_to_have": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Advantages/bonus qualifications as short specific phrases",
                    },
                },
                "required": ["summary", "must_have", "nice_to_have"],
            },
        },
        "required": ["title", "description", "knockout", "bonus", "high_min_bonus", "criteria"],
    },
}


class ParseIn(BaseModel):
    text: str = Field(min_length=20, description="raw JD text")


@router.post("/parse")
def parse_requirements(payload: ParseIn, db: Session = Depends(get_db),
                       _admin: UserSession = Depends(require_admin)) -> dict:
    if llm.provider() is None:
        raise HTTPException(
            503,
            "No LLM API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY) — "
            "fill the rules manually below, or set a key in .env to enable AI parsing",
        )
    try:
        draft, model = llm.tool_call(
            prompt=(
                "Digest this job description into a screening configuration.\n"
                "1) knockout/bonus: map what fits onto the FIXED application form "
                "fields (CGPA, degree field, full-time status, programming languages, "
                "SQL knowledge, AI study, extra-curriculars).\n"
                "2) criteria: distill the FULL requirements of the role into a "
                "screening profile — summary, must_have list, nice_to_have list. "
                "Cover every skill/experience requirement (frameworks, tools, "
                "concepts, soft skills). IGNORE benefits, perks, allowances and "
                "company selling points.\n\n---\n" + payload.text
            ),
            tool_name=PARSE_TOOL["name"],
            description=PARSE_TOOL["description"],
            schema=PARSE_TOOL["input_schema"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("JD parse failed: %s", e)
        raise HTTPException(502, f"AI parsing failed: {e}") from e

    return {
        "title": draft.get("title", ""),
        "description": draft.get("description", ""),
        "requirements": {
            "knockout": draft.get("knockout", {}),
            "bonus": draft.get("bonus", {}),
            "high_min_bonus": draft.get("high_min_bonus", 15),
            "criteria": draft.get("criteria", {}),
        },
        "model": model,
    }


class JobIn(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    requirements: dict = {}


@router.post("", status_code=201)
def create_job(payload: JobIn, db: Session = Depends(get_db),
               _admin: UserSession = Depends(require_admin)) -> dict:
    job = Job(
        title=payload.title,
        description=payload.description,
        requirements=payload.requirements,
        is_open=True,
    )
    db.add(job)
    db.commit()
    return {"id": str(job.id), "title": job.title}


class JobPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    requirements: dict | None = None
    is_open: bool | None = None


@router.patch("/{job_id}")
def update_job(job_id: uuid.UUID, payload: JobPatch, db: Session = Depends(get_db),
               _admin: UserSession = Depends(require_admin)) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if payload.title is not None:
        job.title = payload.title
    if payload.description is not None:
        job.description = payload.description
    if payload.requirements is not None:
        job.requirements = payload.requirements
    if payload.is_open is not None:
        job.is_open = payload.is_open
    db.commit()
    return {"id": str(job.id), "title": job.title, "is_open": job.is_open}


@router.delete("/{job_id}")
def delete_job(job_id: uuid.UUID, db: Session = Depends(get_db),
               _admin: UserSession = Depends(require_admin)) -> dict:
    """Delete a job. Jobs with applications cannot be deleted (data integrity) — close them instead."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    n_apps = db.scalar(
        select(func.count()).select_from(Application).where(Application.job_id == job_id)
    ) or 0
    if n_apps > 0:
        raise HTTPException(
            409,
            f"cannot delete: {n_apps} application(s) reference this job — close it instead",
        )
    db.delete(job)
    db.commit()
    return {"deleted": str(job_id)}


@router.get("/all")
def list_all_jobs(db: Session = Depends(get_db),
                  _admin: UserSession = Depends(require_admin)) -> list[dict]:
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc())).all()
    app_counts = dict(
        db.execute(
            select(Application.job_id, func.count()).group_by(Application.job_id)
        ).all()
    )
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "description": j.description,
            "requirements": j.requirements,
            "is_open": j.is_open,
            "application_count": app_counts.get(j.id, 0),
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs
    ]
