"""职位管理 API(admin)。

- POST /jobs            创建职位(带结构化打分规则)
- PATCH /jobs/{id}      更新规则 / 开关职位
- GET  /jobs/all        管理端列表(含已关闭 + 规则)
- POST /jobs/parse      ★ chat box:把 JD 原文交给 Claude,解析成打分规则草稿
                          (需 ANTHROPIC_API_KEY;无 key 返回 503,前端降级为手动填写)

打分引擎按 job.requirements 动态执行,新职位创建后立即生效,无需改代码。
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

# 解析目标词汇表:必须与 services/scoring.py 的检查逻辑保持一致
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
                        "description": "Accepted degree fields. Use short labels matching the "
                                       "application form where possible: CS, SE, IS, IT, Data Science",
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
            "unmapped": {
                "type": "array", "items": {"type": "string"},
                "description": "Requirements in the JD that CANNOT be expressed with the fields "
                               "above (fixed application form) — list them so the admin knows.",
            },
        },
        "required": ["title", "description", "knockout", "bonus", "high_min_bonus", "unmapped"],
    },
}


class ParseIn(BaseModel):
    text: str = Field(min_length=20, description="JD 原文")


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
                "Extract screening rules from this job description. The application "
                "form has FIXED fields (CGPA, degree field, full-time status, "
                "programming languages, SQL knowledge, AI study, extra-curriculars), "
                "so map requirements onto the tool schema and put anything that "
                "doesn't fit into 'unmapped'.\n\n---\n" + payload.text
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
        },
        "unmapped": draft.get("unmapped", []),
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
    """删除职位。已有申请的职位不可删(数据完整性),请改为关闭。"""
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
