"""SMTP 邮件发送(Gmail:STARTTLS + App Password)。

send_draft:发送一条 email_log 草稿并把状态置为 sent。
SMTP 未配置或发送失败会抛 RuntimeError,调用方决定如何呈现;
自动发送场景(预约确认)失败时不阻塞主流程,邮件保留为 draft 可去 Outbox 重发。
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
    """发送草稿并置 sent;调用方负责 commit。失败抛 RuntimeError,状态保持 draft。"""
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
    """自动发送场景:尽力发送,失败只记日志返回 False(草稿保留,可人工重发)。"""
    try:
        send_draft(db, email)
        return True
    except RuntimeError as e:
        logger.info("auto-send skipped (%s); email %s stays draft", e, email.id)
        return False
