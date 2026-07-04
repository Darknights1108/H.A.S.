"""简历解析:文本提取(PDF/DOCX/TXT)→ LLM 结构化抽取 + 与表单声明交叉核对。

设计原则(项目早期约定):表单是硬门槛判断的主数据源;简历解析只做"佐证情报"
给 admin 看(摘要 + consistency notes),不改变打分结果。
解析在后台线程执行,失败不影响申请流程(status=failed,可人工看原文件)。
"""

import io
import logging
import threading
import uuid

from ..database import SessionLocal
from ..models import Application
from . import llm
from .storage import get_resume

logger = logging.getLogger(__name__)

ALLOWED_EXTS = {".pdf", ".docx", ".txt"}
MAX_SIZE = 5 * 1024 * 1024  # 5MB
MAX_TEXT_CHARS = 15000       # 喂给 LLM 的文本上限

EXTRACT_TOOL = {
    "name": "submit_resume_analysis",
    "description": "Submit the structured analysis of the candidate's resume.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string",
                        "description": "2-3 sentence neutral summary of the candidate"},
            "education": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "field": {"type": "string"},
                    "cgpa": {"type": ["number", "null"]},
                }},
            },
            "experience_projects": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "title": {"type": "string"},
                    "organization": {"type": "string"},
                    "description": {"type": "string"},
                }},
            },
            "programming_languages": {"type": "array", "items": {"type": "string"}},
            "other_skills": {"type": "array", "items": {"type": "string"}},
            "ai_evidence": {
                "type": "array", "items": {"type": "string"},
                "description": "Concrete mentions of AI coursework/projects/experience",
            },
            "extracurricular": {"type": "array", "items": {"type": "string"}},
            "consistency_notes": {
                "type": "array", "items": {"type": "string"},
                "description": "Compare the resume against the application form claims: "
                               "note CONFIRMED claims and any MISMATCH/NOT-FOUND items "
                               "(CGPA, degree field, languages, SQL, AI study).",
            },
        },
        "required": ["summary", "education", "experience_projects",
                     "programming_languages", "other_skills", "ai_evidence",
                     "extracurricular", "consistency_notes"],
    },
}


def extract_text(data: bytes, ext: str) -> str:
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in d.paragraphs)
    else:  # .txt
        text = data.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        raise ValueError("no extractable text in resume")
    return text[:MAX_TEXT_CHARS]


def _form_claims(app_: Application) -> str:
    return (
        f"- CGPA: {app_.cgpa}\n"
        f"- Degree field: {app_.degree_field}\n"
        f"- Full-time student: {app_.is_fulltime}\n"
        f"- Programming languages: {', '.join(app_.prog_langs or []) or 'none'}\n"
        f"- Knows SQL: {app_.has_sql}\n"
        f"- Studied AI: {app_.has_ai_study}\n"
        f"- Extra-curricular: {app_.eca or 'none stated'}"
    )


def _parse(application_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        app_ = db.get(Application, application_id)
        if app_ is None or not app_.resume_file_url:
            return
        try:
            ext = "." + app_.resume_file_url.rsplit(".", 1)[-1].lower()
            data = get_resume(app_.resume_file_url)
            text = extract_text(data, ext)
            parsed, model = llm.tool_call(
                prompt=(
                    "Analyze this resume for an internship screening system.\n\n"
                    "The candidate ALSO filled an application form claiming:\n"
                    f"{_form_claims(app_)}\n\n"
                    "Cross-check the resume against these claims in "
                    "consistency_notes (mark CONFIRMED / MISMATCH / NOT FOUND per "
                    "claim, with evidence).\n\n--- RESUME ---\n" + text
                ),
                tool_name=EXTRACT_TOOL["name"],
                description=EXTRACT_TOOL["description"],
                schema=EXTRACT_TOOL["input_schema"],
                max_tokens=2000,
            )
            app_.resume_parsed = {**parsed, "model": model}
            app_.resume_parse_status = "done"
            logger.info("resume parsed for application %s (%s)", application_id, model)
        except Exception as e:
            logger.warning("resume parse failed for %s: %s", application_id, e)
            app_.resume_parsed = {"error": str(e)}
            app_.resume_parse_status = "failed"
        db.commit()
    finally:
        db.close()


def parse_resume_async(application_id: uuid.UUID) -> None:
    """提交后台线程解析;不阻塞申请提交。"""
    threading.Thread(target=_parse, args=(application_id,), daemon=True).start()
