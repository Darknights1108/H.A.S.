"""候选人信件模板(统一措辞;公司名读 app_setting.company_name)。

reject 模板按用户提供的范本(Infineon 风格):
  We have carefully reviewed ... regret to inform you ...
  (可选 talent bank 段)
  We wish you good luck ...
  Best Regards, {company} Recruiting Team
offer 模板为占位版本 —— 具体 offer letter 内容待定,结构先立起来。
"""

from sqlalchemy.orm import Session

from ..models import AppSetting, Candidate, Job


def get_company_name(db: Session, default: str = "HAS") -> str:
    row = db.get(AppSetting, "company_name")
    if row is None:
        return default
    value = row.value
    return str(value).strip('"') if value else default


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
    # 占位版 offer letter:正式内容待定,先保证流程与签名结构完整
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
