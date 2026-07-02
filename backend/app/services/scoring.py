"""打分引擎:硬门槛(knockout)+ 加分项(bonus)→ band。

规则来自 job.requirements(jsonb),例:
{
  "knockout": { "min_cgpa": 3.20, "fields": ["CS","SE","IS","IT","Data Science"],
                "require_fulltime": true, "langs_any": ["Python","PHP"], "require_sql": true },
  "bonus":    { "ai_study": 10, "eca": 8, "extra_lang": 5 },
  "high_min_bonus": 15
}

任一硬门槛不过 → Low;全过 → 按加分总分定 High(≥ high_min_bonus)/ Medium。
理由(reasoning):有 ANTHROPIC_API_KEY 时用 Claude 润色,否则规则模板生成。
"""

import logging

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Application, Job, Score

logger = logging.getLogger(__name__)

RULES_VERSION = "rules-v1"
LLM_MODEL = "claude-haiku-4-5"


def _knockout_checks(app_: Application, ko: dict) -> dict[str, dict]:
    """逐项硬门槛检查,返回 {项: {passed, detail}}。"""
    checks: dict[str, dict] = {}
    if "min_cgpa" in ko:
        passed = app_.cgpa is not None and float(app_.cgpa) >= float(ko["min_cgpa"])
        checks["cgpa"] = {
            "passed": passed,
            "detail": f"CGPA {app_.cgpa} vs required ≥ {ko['min_cgpa']}",
        }
    if ko.get("fields"):
        passed = app_.degree_field in ko["fields"]
        checks["degree_field"] = {
            "passed": passed,
            "detail": f"field '{app_.degree_field}' vs accepted {ko['fields']}",
        }
    if ko.get("require_fulltime"):
        checks["fulltime"] = {
            "passed": bool(app_.is_fulltime),
            "detail": f"full-time student: {app_.is_fulltime}",
        }
    if ko.get("langs_any"):
        passed = any(l in (app_.prog_langs or []) for l in ko["langs_any"])
        checks["programming"] = {
            "passed": passed,
            "detail": f"knows {app_.prog_langs} vs any of {ko['langs_any']}",
        }
    if ko.get("require_sql"):
        checks["sql"] = {"passed": app_.has_sql, "detail": f"SQL knowledge: {app_.has_sql}"}
    return checks


def _bonus_points(app_: Application, bonus_cfg: dict) -> dict[str, float]:
    points: dict[str, float] = {}
    if app_.has_ai_study and bonus_cfg.get("ai_study"):
        points["ai_study"] = float(bonus_cfg["ai_study"])
    if app_.eca and app_.eca.strip() and bonus_cfg.get("eca"):
        points["eca"] = float(bonus_cfg["eca"])
    if len(app_.prog_langs or []) > 1 and bonus_cfg.get("extra_lang"):
        points["extra_lang"] = float(bonus_cfg["extra_lang"])
    return points


def _template_reasoning(
    knockout: dict[str, dict], bonus: dict[str, float], band: str, total: float
) -> str:
    lines: list[str] = []
    failed = [f"{k}: {v['detail']}" for k, v in knockout.items() if not v["passed"]]
    if failed:
        lines.append("Knockout criteria FAILED → Low band:")
        lines += [f"  ✗ {f}" for f in failed]
    else:
        lines.append("All knockout criteria passed:")
        lines += [f"  ✓ {k}: {v['detail']}" for k, v in knockout.items()]
        if bonus:
            lines.append(f"Bonus points ({total:g} total):")
            lines += [f"  + {k}: {v:g}" for k, v in bonus.items()]
        else:
            lines.append("No bonus points earned.")
        lines.append(f"Band: {band.upper()}")
    return "\n".join(lines)


def _llm_reasoning(template: str, band: str) -> str | None:
    """有 API key 时让 Claude 把规则结果写成一段简洁的评审说明;失败则返回 None 走模板。"""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=LLM_MODEL,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are a hiring screening assistant. Rewrite the following "
                        "rule-based screening result as a concise, neutral 2-4 sentence "
                        "explanation for an admin reviewer. Do not change any facts or "
                        f"the band ({band}).\n\n{template}"
                    ),
                }
            ],
        )
        return msg.content[0].text.strip()
    except Exception as e:  # 网络/额度等问题一律降级,不阻塞打分
        logger.warning("LLM reasoning failed, falling back to template: %s", e)
        return None


def score_application(db: Session, app_: Application) -> Score:
    """打分并写 score 行(不 commit);调用方负责状态流转与 commit。"""
    job = db.get(Job, app_.job_id)
    req = job.requirements or {}
    knockout = _knockout_checks(app_, req.get("knockout", {}))
    knockout_passed = all(v["passed"] for v in knockout.values())

    bonus = _bonus_points(app_, req.get("bonus", {})) if knockout_passed else {}
    total = sum(bonus.values())
    high_min = float(req.get("high_min_bonus", 15))
    band = "low" if not knockout_passed else ("high" if total >= high_min else "medium")

    template = _template_reasoning(knockout, bonus, band, total)
    llm_text = _llm_reasoning(template, band)

    score = Score(
        application_id=app_.id,
        knockout_passed=knockout_passed,
        band=band,
        total_score=total,
        breakdown={"knockout": knockout, "bonus": bonus, "high_min_bonus": high_min},
        reasoning=llm_text or template,
        model=LLM_MODEL if llm_text else RULES_VERSION,
    )
    db.add(score)
    return score
