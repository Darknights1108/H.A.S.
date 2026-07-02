"""Magic-link 认证核心:令牌/会话哈希、FastAPI 依赖(会话校验、角色守卫)、审计日志。

安全要点:
- 令牌与会话 cookie 均为 secrets.token_urlsafe(48) 随机值,数据库只存 sha256 哈希
- 会话存服务端(user_session 表),可随时吊销;cookie 为 HttpOnly + SameSite=Lax
- 生产环境置 COOKIE_SECURE=true(HTTPS)
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
    """从 cookie 解析有效会话;无/过期/已吊销一律 401。"""
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
    """按邮箱取(或创建)对应的面试官记录 —— 非 admin 角色认领时段时的身份。"""
    itv = db.scalar(select(Interviewer).where(Interviewer.email == email))
    if itv is None:
        itv = Interviewer(name=name or email.split("@")[0], email=email)
        db.add(itv)
        db.flush()
    return itv
