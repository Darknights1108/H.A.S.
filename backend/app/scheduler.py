"""定时任务:每天扫描 shortlist,把超过配置天数无人审查的申请自动淘汰。"""

import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .database import SessionLocal

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _reject_with_letter(db, app_, reason: str) -> None:
    from .models import Candidate, Job
    from .services.scheduling import draft_email
    from .services.templates import rejection_email

    candidate = db.get(Candidate, app_.candidate_id)
    job = db.get(Job, app_.job_id)
    app_.status = "rejected"
    app_.rejected_reason = reason
    subject, body = rejection_email(db, candidate, job, after_interview=False)
    draft_email(db, app_, "reject", subject, body)


def expire_stale_shortlist() -> int:
    """无人审 timer:shortlisted 超过 shortlist_review_days 且【尚未发出邀请】的,自动淘汰。

    已发出邀请的申请视为"已审查",交给 expire_no_response 处理。
    """
    from sqlalchemy import exists

    from .models import Application, EmailLog
    from .services.scheduling import get_setting_int

    db = SessionLocal()
    try:
        days = get_setting_int(db, "shortlist_review_days", 7)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        invite_sent = exists(
            select(EmailLog.id).where(
                EmailLog.application_id == Application.id,
                EmailLog.type == "invite",
                EmailLog.status == "sent",
            )
        )
        stale = db.scalars(
            select(Application).where(
                Application.status == "shortlisted",
                Application.shortlisted_at < cutoff,
                ~invite_sent,
            )
        ).all()
        for app_ in stale:
            _reject_with_letter(db, app_, "auto_no_review")
        db.commit()
        if stale:
            logger.info("auto-expired %d unreviewed shortlisted application(s)", len(stale))
        return len(stale)
    finally:
        db.close()


def expire_no_response() -> int:
    """候选人无响应 timer:邀请已发出超过 candidate_response_days 仍未预约(状态还在
    shortlisted)的,自动淘汰。"""
    from sqlalchemy import func

    from .models import Application, EmailLog
    from .services.scheduling import get_setting_int

    db = SessionLocal()
    try:
        days = get_setting_int(db, "candidate_response_days", 7)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        rows = db.execute(
            select(Application, func.max(EmailLog.sent_at))
            .join(EmailLog, EmailLog.application_id == Application.id)
            .where(
                Application.status == "shortlisted",
                EmailLog.type == "invite",
                EmailLog.status == "sent",
            )
            .group_by(Application.id)
        ).all()
        expired = 0
        for app_, last_sent in rows:
            if last_sent is not None and last_sent < cutoff:
                _reject_with_letter(db, app_, "no_response")
                expired += 1
        db.commit()
        if expired:
            logger.info("auto-expired %d no-response application(s)", expired)
        return expired
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Kuala_Lumpur")
    # 每天 02:00 / 02:05 MYT
    _scheduler.add_job(expire_stale_shortlist, "cron", hour=2, id="expire_shortlist")
    _scheduler.add_job(expire_no_response, "cron", hour=2, minute=5, id="expire_no_response")
    _scheduler.start()
    logger.info("scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
