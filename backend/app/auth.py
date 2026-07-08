"""Auth core: token/session hashing, FastAPI dependencies (session check, role
guards) and audit logging.

Security notes:
- Session cookie values are secrets.token_urlsafe(48); only sha256 hashes are stored
- Sessions are server-side (user_session table) and revocable at any time;
  the cookie is HttpOnly + SameSite=Lax
- Set COOKIE_SECURE=true in production (HTTPS)
"""

import datetime
import hashlib
import secrets

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuthLog, Interviewer, UserSession

SESSION_COOKIE = "has_session"


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def new_raw_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def log_auth(
    db: Session, event: str, email: str | None = None,
    ip: str | None = None, detail: str | None = None,
) -> None:
    db.add(AuthLog(event=event, email=email, ip=ip, detail=detail))


def get_session(
    db: Session = Depends(get_db),
    has_session: str | None = Cookie(default=None),
) -> UserSession:
    """Resolve a valid session from the cookie; missing/expired/revoked -> 401."""
    if not has_session:
        raise HTTPException(401, "not authenticated")
    row = db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_token(has_session))
    )
    if row is None or row.revoked_at is not None or row.expires_at < utcnow():
        raise HTTPException(401, "session expired or invalid")
    return row


def require_admin(sess: UserSession = Depends(get_session)) -> UserSession:
    if sess.role != "admin":
        raise HTTPException(403, "admin only")
    return sess


def resolve_interviewer(db: Session, email: str, name: str | None = None) -> Interviewer:
    """Get (or create) the interviewer record for an email — the acting identity for non-admin staff."""
    itv = db.scalar(select(Interviewer).where(Interviewer.email == email))
    if itv is None:
        itv = Interviewer(name=name or email.split("@")[0], email=email)
        db.add(itv)
        db.flush()
    return itv
