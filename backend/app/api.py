"""Basic API: health check + global settings (admin view/update)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import log_auth, require_admin
from .database import get_db
from .models import AppSetting, UserSession

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Type and value range per setting key (prevents invalid configuration)
SETTING_RULES: dict[str, dict] = {
    "shortlist_review_days": {"type": "int", "min": 1, "max": 90},
    "slot_duration_minutes": {"type": "int", "min": 15, "max": 240},
    "panel_max_interviewers": {"type": "int", "min": 1, "max": 20},
    "reschedule_max": {"type": "int", "min": 0, "max": 20},  # 0 = unlimited
    "candidate_response_days": {"type": "int", "min": 1, "max": 90},
    "low_reject_send_days": {"type": "int", "min": 0, "max": 30},
    "work_start_hour": {"type": "int", "min": 0, "max": 23},
    "work_end_hour": {"type": "int", "min": 1, "max": 24},
    "company_name": {"type": "str", "min_len": 1, "max_len": 80},
    "invite_email_subject": {"type": "str", "min_len": 1, "max_len": 200},
    "invite_email_template": {"type": "str", "min_len": 1, "max_len": 4000, "multiline": True},
}


@router.get("/settings")
def list_settings(db: Session = Depends(get_db),
                  _admin: UserSession = Depends(require_admin)) -> list[dict]:
    rows = db.scalars(select(AppSetting).order_by(AppSetting.key)).all()
    return [
        {
            "key": r.key,
            "value": r.value,
            "description": r.description,
            "type": SETTING_RULES.get(r.key, {}).get("type", "str"),
            "multiline": SETTING_RULES.get(r.key, {}).get("multiline", False),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


class SettingIn(BaseModel):
    value: int | str


@router.patch("/settings/{key}")
def update_setting(key: str, payload: SettingIn, db: Session = Depends(get_db),
                   admin: UserSession = Depends(require_admin)) -> dict:
    row = db.get(AppSetting, key)
    if row is None:
        raise HTTPException(404, "setting not found")
    rule = SETTING_RULES.get(key)
    if rule is None:
        raise HTTPException(422, "this setting is not editable")

    if rule["type"] == "int":
        try:
            value: int | str = int(payload.value)
        except (TypeError, ValueError):
            raise HTTPException(422, "value must be an integer")
        if not (rule["min"] <= value <= rule["max"]):
            raise HTTPException(422, f"value must be between {rule['min']} and {rule['max']}")
    else:
        value = str(payload.value).strip()
        if not (rule["min_len"] <= len(value) <= rule["max_len"]):
            raise HTTPException(422, f"length must be {rule['min_len']}-{rule['max_len']} chars")

    from sqlalchemy import func

    row.value = value
    row.updated_at = func.now()
    log_auth(db, "setting_update", admin.email, detail=f"{key}={value!r}")
    db.commit()
    return {"key": key, "value": row.value}
