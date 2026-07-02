"""Outbox API:邮件草稿列表 + 人工审核发送。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..config import settings
from ..database import get_db
from ..models import Application, Candidate, EmailLog, UserSession
from ..services.mailer import send_draft

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("")
def list_emails(db: Session = Depends(get_db),
                _admin: UserSession = Depends(require_admin)) -> dict:
    rows = db.execute(
        select(EmailLog, Candidate)
        .join(Application, Application.id == EmailLog.application_id)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .order_by(EmailLog.created_at.desc())
    ).all()
    return {
        "smtp_configured": settings.smtp_configured,
        "emails": [
            {
                "id": str(e.id),
                "type": e.type,
                "to": c.email,
                "candidate_name": c.name,
                "subject": e.subject,
                "body": e.body,
                "status": e.status,
                "created_at": e.created_at.isoformat(),
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            }
            for e, c in rows
        ],
    }


@router.post("/{email_id}/send")
def send_email(email_id: uuid.UUID, db: Session = Depends(get_db),
               _admin: UserSession = Depends(require_admin)) -> dict:
    email = db.get(EmailLog, email_id)
    if email is None:
        raise HTTPException(404, "email not found")
    try:
        send_draft(db, email)
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    db.commit()
    return {"id": str(email.id), "status": email.status, "sent_at": email.sent_at.isoformat()}
