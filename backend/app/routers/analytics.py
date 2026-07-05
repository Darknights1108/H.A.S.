"""Analytics API:招聘漏斗与运营指标聚合(admin)。"""

import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import (
    Application,
    Candidate,
    EmailLog,
    Interview,
    Interviewer,
    Job,
    Score,
    Slot,
    SlotInterviewer,
    UserSession,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def analytics(db: Session = Depends(get_db),
              _admin: UserSession = Depends(require_admin)) -> dict:
    today = datetime.date.today()

    total_apps = db.scalar(select(func.count()).select_from(Application)) or 0
    total_candidates = db.scalar(select(func.count()).select_from(Candidate)) or 0
    open_jobs = db.scalar(select(func.count()).select_from(Job).where(Job.is_open)) or 0

    status_counts = dict(
        db.execute(select(Application.status, func.count()).group_by(Application.status)).all()
    )
    band_counts = dict(
        db.execute(select(Score.band, func.count()).group_by(Score.band)).all()
    )
    rejection_reasons = dict(
        db.execute(
            select(Application.rejected_reason, func.count())
            .where(Application.status == "rejected", Application.rejected_reason.isnot(None))
            .group_by(Application.rejected_reason)
        ).all()
    )

    invite_sent = db.scalar(
        select(func.count(distinct(EmailLog.application_id))).where(
            EmailLog.type == "invite", EmailLog.status == "sent"
        )
    ) or 0
    booked = db.scalar(select(func.count(distinct(Interview.application_id)))) or 0
    outcome_done = db.scalar(
        select(func.count()).select_from(Interview).where(Interview.status.in_(["passed", "failed"]))
    ) or 0
    passed = status_counts.get("passed", 0)

    # 漏斗:各阶段"到达过"的申请数(累进)
    screened_ok = (band_counts.get("high", 0) or 0) + (band_counts.get("medium", 0) or 0)
    funnel = [
        {"stage": "Applications received", "count": total_apps},
        {"stage": "Passed screening (High/Medium)", "count": screened_ok},
        {"stage": "Invite sent", "count": invite_sent},
        {"stage": "Interview booked", "count": booked},
        {"stage": "Outcome recorded", "count": outcome_done},
        {"stage": "Passed (offer)", "count": passed},
    ]

    per_job = [
        {"title": title, "applications": apps, "passed": passed_n}
        for title, apps, passed_n in db.execute(
            select(
                Job.title,
                func.count(Application.id),
                func.count(Application.id).filter(Application.status == "passed"),
            )
            .join(Application, Application.job_id == Job.id, isouter=True)
            .group_by(Job.id, Job.title)
            .order_by(func.count(Application.id).desc())
        ).all()
    ]

    since = today - datetime.timedelta(days=13)
    daily_rows = dict(
        db.execute(
            select(cast(Application.submitted_at, Date), func.count())
            .where(cast(Application.submitted_at, Date) >= since)
            .group_by(cast(Application.submitted_at, Date))
        ).all()
    )
    daily = [
        {"date": (since + datetime.timedelta(days=i)).isoformat(),
         "count": daily_rows.get(since + datetime.timedelta(days=i), 0)}
        for i in range(14)
    ]

    slot_counts = dict(
        db.execute(
            select(Slot.status, func.count())
            .where(Slot.slot_date >= today)
            .group_by(Slot.status)
        ).all()
    )

    interviewer_load = [
        {"name": name, "claimed": claimed, "booked": booked_n}
        for name, claimed, booked_n in db.execute(
            select(
                Interviewer.name,
                func.count(SlotInterviewer.slot_id),
                func.count(SlotInterviewer.slot_id).filter(Slot.status == "booked"),
            )
            .join(SlotInterviewer, SlotInterviewer.interviewer_id == Interviewer.id, isouter=True)
            .join(Slot, Slot.id == SlotInterviewer.slot_id, isouter=True)
            .group_by(Interviewer.id, Interviewer.name)
            .order_by(func.count(SlotInterviewer.slot_id).desc())
        ).all()
    ]

    # 提交到预约的平均天数
    avg_secs = db.scalar(
        select(func.avg(func.extract("epoch", Interview.created_at - Application.submitted_at)))
        .select_from(Interview)
        .join(Application, Application.id == Interview.application_id)
    )
    avg_days_to_book = round(float(avg_secs) / 86400, 1) if avg_secs is not None else None

    return {
        "overview": {
            "total_applications": total_apps,
            "total_candidates": total_candidates,
            "open_jobs": open_jobs,
            "offers": passed,
            "avg_days_to_book": avg_days_to_book,
        },
        "funnel": funnel,
        "bands": {b: band_counts.get(b, 0) for b in ("high", "medium", "low")},
        "statuses": status_counts,
        "rejection_reasons": rejection_reasons,
        "per_job": per_job,
        "daily_applications": daily,
        "slots": {
            "open": slot_counts.get("open", 0),
            "booked": slot_counts.get("booked", 0),
            "empty": slot_counts.get("empty", 0),
        },
        "interviewer_load": interviewer_load,
    }
