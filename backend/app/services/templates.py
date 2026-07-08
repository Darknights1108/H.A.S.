"""Candidate letter templates (consistent wording; company name from
app_setting.company_name).

The rejection template follows the sample supplied by the user (corporate
style): "We have carefully reviewed ... regret to inform you ..." with an
optional talent-bank paragraph, closed by "Best Regards, {company} Recruiting
Team". The offer template is a placeholder — final wording TBD.
"""

from sqlalchemy.orm import Session

from ..models import AppSetting, Candidate, Job


def get_setting_str(db: Session, key: str, default: str) -> str:
    row = db.get(AppSetting, key)
    if row is None or not row.value:
        return default
    return str(row.value)


def get_company_name(db: Session, default: str = "HAS") -> str:
    return get_setting_str(db, "company_name", default).strip('"')


def _render(template: str, mapping: dict[str, str]) -> str:
    """Replace placeholders one by one; unknown {xxx} stay as-is, never crash."""
    for k, v in mapping.items():
        template = template.replace("{" + k + "}", str(v))
    return template


DEFAULT_INVITE_SUBJECT = "Interview invitation — {job_title}"
DEFAULT_INVITE_BODY = (
    "Hi {candidate_name},\n\n"
    "Congratulations! You have been shortlisted for {job_title}.\n\n"
    "Please pick an interview time that suits you using your personal "
    "booking link:\n{booking_url}\n\n"
    "All interviews are conducted online (times in MYT, UTC+08:00).\n\n"
    "Best Regards,\n{company_name} Recruiting Team\n"
)


def invite_email(
    db: Session, candidate: Candidate, job: Job, booking_url: str
) -> tuple[str, str]:
    """Invite email: subject/body templates are editable in admin settings."""
    mapping = {
        "candidate_name": candidate.name,
        "job_title": job.title,
        "booking_url": booking_url,
        "company_name": get_company_name(db),
    }
    subject = _render(get_setting_str(db, "invite_email_subject", DEFAULT_INVITE_SUBJECT), mapping)
    body = _render(get_setting_str(db, "invite_email_template", DEFAULT_INVITE_BODY), mapping)
    return subject, body


def rejection_email(
    db: Session, candidate: Candidate, job: Job, *, after_interview: bool
) -> tuple[str, str]:
    company = get_company_name(db)
    stage = (
        "your interview" if after_interview else "your application"
    )
    subject = f"Your application — {job.title}"
    talent_bank_para = (
        "Your profile has been kept in our talent bank and we will reach out "
        "when a new position matches your background.\n\n"
        if candidate.consent_talent_bank
        else ""
    )
    body = (
        f"Dear {candidate.name},\n\n"
        f"We have carefully reviewed {stage} for the position „{job.title}“ "
        f"and regret to inform you that we will not be moving forward with "
        f"your application at this time.\n\n"
        f"{talent_bank_para}"
        f"We wish you good luck with your job search and future endeavors.\n\n"
        f"Best Regards,\n"
        f"{company} Recruiting Team\n"
    )
    return subject, body


def offer_email(db: Session, candidate: Candidate, job: Job) -> tuple[str, str]:
    company = get_company_name(db)
    subject = f"Offer — {job.title}"
    # Placeholder offer letter: final wording TBD; flow and signature structure in place
    body = (
        f"Dear {candidate.name},\n\n"
        f"Congratulations! Following your interview, we are pleased to offer "
        f"you the position „{job.title}“ at {company}.\n\n"
        f"Our team will contact you shortly with the formal offer letter, "
        f"including the start date, compensation details, and onboarding "
        f"documents. If you have any questions in the meantime, simply reply "
        f"to this email.\n\n"
        f"We look forward to having you on board.\n\n"
        f"Best Regards,\n"
        f"{company} Recruiting Team\n"
    )
    return subject, body
