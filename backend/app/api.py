from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AppSetting

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/settings")
def list_settings(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AppSetting)).all()
    return [
        {"key": r.key, "value": r.value, "description": r.description}
        for r in rows
    ]
