"""SMTP email sending (Gmail: STARTTLS + App Password).

send_draft: send an email_log draft and mark it sent.
Raises RuntimeError when SMTP is unconfigured or sending fails; callers decide
how to surface it. Auto-send paths (booking confirmations) never block the main
flow — the email stays a draft and can be re-sent from the outbox.
"""

import datetime
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Application, Candidate, EmailLog

logger = logging.getLogger(__name__)


def send_raw(to: str, subject: str, body: str) -> None:
    if not settings.smtp_configured:
        raise RuntimeError(
            "SMTP not configured — set SMTP_HOST/SMTP_USER/SMTP_PASSWORD in .env"
        )
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def send_draft(db: Session, email: EmailLog) -> None:
    """Send a draft and mark it sent; caller commits. Raises RuntimeError on failure, status stays draft."""
    if email.status == "sent":
        raise RuntimeError("email already sent")
    app_ = db.get(Application, email.application_id)
    candidate = db.get(Candidate, app_.candidate_id)
    try:
        send_raw(candidate.email, email.subject, email.body)
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("SMTP send failed for email %s: %s", email.id, e)
        raise RuntimeError(f"send failed: {e}") from e
    email.status = "sent"
    email.sent_at = datetime.datetime.now(datetime.timezone.utc)


def try_send_draft(db: Session, email: EmailLog) -> bool:
    """Auto-send path: best effort; on failure just log and return False (draft kept for manual send)."""
    try:
        send_draft(db, email)
        return True
    except RuntimeError as e:
        logger.info("auto-send skipped (%s); email %s stays draft", e, email.id)
        return False
