"""定时任务:每天扫描 shortlist,把超过配置天数无人审查的申请自动淘汰。"""

import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .database import SessionLocal

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def expire_stale_shortlist() -> int:
    """status='shortlisted' 且 shortlisted_at 早于 (now - 配置天数) 的,转 rejected 并草拟婉拒信。

    天数从 app_setting.shortlist_review_days 读取,admin 改设置即时生效。
    """
    from .models import Application, Candidate, Job
    from .services.scheduling import draft_email, get_setting_int
    from .services.templates import rejection_email

    db = SessionLocal()
    try:
        days = get_setting_int(db, "shortlist_review_days", 7)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        stale = db.scalars(
            select(Application).where(
                Application.status == "shortlisted",
                Application.shortlisted_at < cutoff,
            )
        ).all()
        for app_ in stale:
            candidate = db.get(Candidate, app_.candidate_id)
            job = db.get(Job, app_.job_id)
            app_.status = "rejected"
            app_.rejected_reason = "auto_no_review"
            subject, body = rejection_email(db, candidate, job, after_interview=False)
            draft_email(db, app_, "reject", subject, body)
        db.commit()
        if stale:
            logger.info("auto-expired %d shortlisted application(s)", len(stale))
        return len(stale)
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Kuala_Lumpur")
    # 每天 02:00 MYT 跑一次
    _scheduler.add_job(expire_stale_shortlist, "cron", hour=2, id="expire_shortlist")
    _scheduler.start()
    logger.info("scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
