"""Resume parsing: text extraction (PDF/DOCX/TXT) -> structured LLM extraction
+ cross-check against form claims.

Design principle (agreed early in the project): the form is the primary source
for knockout checks; resume parsing is supporting intelligence for the admin
(summary + consistency notes) and never changes the score.
Parsing runs in a background thread; failures never affect the application flow
(status=failed, the original file remains viewable).
"""

import io
import logging
import threading
import uuid

from ..database import SessionLocal
from ..models import Application, Job
from . import llm
from .storage import get_resume

logger = logging.getLogger(__name__)

ALLOWED_EXTS = {".pdf", ".docx", ".txt"}
MAX_SIZE = 5 * 1024 * 1024  # 5MB
MAX_TEXT_CHARS = 15000       # max characters fed to the LLM

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
            "jd_match": {
                "type": "object",
                "description": "Evaluation of the resume against the JOB SCREENING PROFILE "
                               "(only when one is provided in the prompt).",
                "properties": {
                    "must_have": {
                        "type": "array",
                        "items": {"type": "object", "properties": {
                            "criterion": {"type": "string"},
                            "met": {"type": "string", "enum": ["yes", "partial", "no", "unknown"]},
                            "evidence": {"type": "string",
                                         "description": "Short quote/paraphrase from the resume, "
                                                        "or why it is not met"},
                        }, "required": ["criterion", "met", "evidence"]},
                    },
                    "nice_to_have": {
                        "type": "array",
                        "items": {"type": "object", "properties": {
                            "criterion": {"type": "string"},
                            "met": {"type": "string", "enum": ["yes", "partial", "no", "unknown"]},
                            "evidence": {"type": "string"},
                        }, "required": ["criterion", "met", "evidence"]},
                    },
                    "match_score": {"type": "number",
                                    "description": "0-100 overall fit against the profile"},
                    "verdict": {"type": "string",
                                "description": "2-3 sentence hiring-fit summary"},
                },
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
            job = db.get(Job, app_.job_id)
            criteria = ((job.requirements or {}).get("criteria") or {}) if job else {}
            profile_block = ""
            if criteria.get("must_have") or criteria.get("nice_to_have"):
                mh = "".join(f"- {x}\n" for x in criteria.get("must_have", []))
                nh = "".join(f"- {x}\n" for x in criteria.get("nice_to_have", []))
                profile_block = (
                    "JOB SCREENING PROFILE (evaluate the resume against EVERY item "
                    "below in jd_match, with met=yes/partial/no/unknown and concrete "
                    "evidence; then give match_score 0-100 and a verdict):\n"
                    f"Role summary: {criteria.get('summary', '')}\n"
                    f"MUST HAVE:\n{mh}NICE TO HAVE:\n{nh}\n"
                )
            parsed, model = llm.tool_call(
                prompt=(
                    "Analyze this resume for a hiring screening system.\n\n"
                    f"{profile_block}"
                    "The candidate ALSO filled an application form claiming:\n"
                    f"{_form_claims(app_)}\n\n"
                    "Cross-check the resume against these claims in "
                    "consistency_notes (mark CONFIRMED / MISMATCH / NOT FOUND per "
                    "claim, with evidence)."
                    + ("" if profile_block else " Omit jd_match — no profile provided.")
                    + "\n\n--- RESUME ---\n" + text
                ),
                tool_name=EXTRACT_TOOL["name"],
                description=EXTRACT_TOOL["description"],
                schema=EXTRACT_TOOL["input_schema"],
                max_tokens=3000,
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
    """Kick off background parsing; never blocks submission."""
    threading.Thread(target=_parse, args=(application_id,), daemon=True).start()
