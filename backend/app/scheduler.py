"""定时任务:每天扫描 shortlist,把超过配置天数无人审查的申请自动淘汰。"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from .database import SessionLocal

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def expire_stale_shortlist() -> int:
    """status='shortlisted' 且 shortlisted_at 早于 (now - 配置天数) 的,转 rejected。

    天数从 app_setting.shortlist_review_days 读取,admin 改设置即时生效。
    """
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                """
                UPDATE application a
                SET status = 'rejected',
                    rejected_reason = 'auto_no_review',
                    updated_at = now()
                FROM (
                    SELECT (value #>> '{}')::int AS days
                    FROM app_setting WHERE key = 'shortlist_review_days'
                ) s
                WHERE a.status = 'shortlisted'
                  AND a.shortlisted_at < now() - make_interval(days => COALESCE(s.days, 7))
                """
            )
        )
        db.commit()
        count = result.rowcount or 0
        if count:
            logger.info("auto-expired %d shortlisted application(s)", count)
        return count
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
