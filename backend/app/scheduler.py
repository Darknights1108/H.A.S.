"""Scheduled jobs: daily scans that auto-expire stale applications and auto-send letters."""

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
    """No-review timer: auto-reject applications shortlisted longer than
    shortlist_review_days that have NOT had an invite sent.

    Applications with a sent invite count as reviewed and are handled by
    expire_no_response instead.
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
    """Candidate no-response timer: auto-reject applications whose invite was sent
    more than candidate_response_days ago but still have no booking (status
    still shortlisted)."""
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


def auto_send_low_reject_emails() -> int:
    """Low-band rejection letters: auto-send drafts once they are N days old.

    Other rejection letters (manual / interview failed / timers) still require
    a manual send from the outbox. Failures keep the draft and retry next day.
    """
    from sqlalchemy import select as _select

    from .models import Application, EmailLog
    from .services.mailer import try_send_draft
    from .services.scheduling import get_setting_int

    db = SessionLocal()
    try:
        days = get_setting_int(db, "low_reject_send_days", 2)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        drafts = db.scalars(
            _select(EmailLog)
            .join(Application, Application.id == EmailLog.application_id)
            .where(
                EmailLog.type == "reject",
                EmailLog.status == "draft",
                EmailLog.created_at < cutoff,
                Application.rejected_reason == "low_band",
            )
        ).all()
        sent = 0
        for email in drafts:
            if try_send_draft(db, email):
                sent += 1
        db.commit()
        if sent:
            logger.info("auto-sent %d low-band rejection letter(s)", sent)
        return sent
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Kuala_Lumpur")
    # Daily at 02:00 / 02:05 MYT
    _scheduler.add_job(expire_stale_shortlist, "cron", hour=2, id="expire_shortlist")
    _scheduler.add_job(expire_no_response, "cron", hour=2, minute=5, id="expire_no_response")
    _scheduler.add_job(auto_send_low_reject_emails, "cron", hour=2, minute=10,
                       id="auto_send_low_reject")
    _scheduler.start()
    logger.info("scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
