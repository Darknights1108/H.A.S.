"""Magic-link 登录 + 白名单管理 API。

登录流:
  POST /auth/request-link  输入邮箱 → 白名单+限流校验 → 发一次性链接(统一泛化回复,不泄露是否在册)
  POST /auth/verify        校验令牌(未过期/未用过/邮箱仍 enabled)→ 标记已用 → 建会话 → 种 cookie
  GET  /auth/me            当前会话信息
  POST /auth/logout        吊销会话 + 清 cookie

白名单(admin):GET/POST /auth/allowlist,PATCH/DELETE /auth/allowlist/{id}
所有关键动作写入 auth_log。
"""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import (
    SESSION_COOKIE,
    get_session,
    hash_token,
    log_auth,
    new_raw_token,
    require_admin,
    resolve_interviewer,
    utcnow,
)
from ..config import settings
from ..database import get_db
from ..models import AllowedEmail, Interviewer, LoginToken, UserSession
from ..services.mailer import send_raw

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_MSG = "Please check your email. If this email is allowed, a login link will be sent."
ROLES = ("admin", "interviewer", "lecturer", "supervisor", "user")
# 限流窗口:同邮箱 15 分钟最多 3 次;同 IP 15 分钟最多 10 次
RATE_WINDOW_MIN = 15
RATE_MAX_PER_EMAIL = 3
RATE_MAX_PER_IP = 10


class RequestLinkIn(BaseModel):
    email: EmailStr


@router.post("/request-link")
def request_link(payload: RequestLinkIn, request: Request, db: Session = Depends(get_db)) -> dict:
    email = payload.email.lower().strip()
    ip = request.client.host if request.client else None
    since = utcnow() - datetime.timedelta(minutes=RATE_WINDOW_MIN)

    def generic(extra: dict | None = None) -> dict:
        db.commit()
        out = {"message": GENERIC_MSG}
        if extra:
            out.update(extra)
        return out

    entry = db.scalar(select(AllowedEmail).where(AllowedEmail.email == email))
    if entry is None or not entry.enabled:
        # 不发送、不泄露;仅记审计
        log_auth(db, "magic_link_denied", email, ip,
                 "not in allowlist" if entry is None else "disabled")
        return generic()

    # 限流(静默拒绝,响应仍泛化)
    n_email = db.scalar(
        select(func.count()).select_from(LoginToken)
        .where(LoginToken.email == email, LoginToken.created_at > since)
    ) or 0
    n_ip = 0
    if ip:
        n_ip = db.scalar(
            select(func.count()).select_from(LoginToken)
            .where(LoginToken.request_ip == ip, LoginToken.created_at > since)
        ) or 0
    if n_email >= RATE_MAX_PER_EMAIL or n_ip >= RATE_MAX_PER_IP:
        log_auth(db, "magic_link_rate_limited", email, ip,
                 f"email:{n_email} ip:{n_ip} in {RATE_WINDOW_MIN}min")
        return generic()

    raw = new_raw_token()
    db.add(LoginToken(
        email=email,
        token_hash=hash_token(raw),
        request_ip=ip,
        expires_at=utcnow() + datetime.timedelta(minutes=settings.magic_link_ttl_minutes),
    ))
    link = f"{settings.frontend_base_url}/auth/verify?token={raw}"
    try:
        send_raw(
            email,
            "Your HAS login link",
            (
                f"Hi{f' {entry.name}' if entry.name else ''},\n\n"
                f"Click the link below to sign in to HAS. "
                f"It expires in {settings.magic_link_ttl_minutes} minutes and can be used once.\n\n"
                f"{link}\n\n"
                f"If you did not request this, you can safely ignore this email.\n"
            ),
        )
        log_auth(db, "magic_link_requested", email, ip)
    except Exception as e:
        log_auth(db, "magic_link_send_failed", email, ip, str(e))
    # 开发模式可直接回传链接,便于本地/自动化测试;生产必须关闭
    return generic({"debug_link": link} if settings.debug_expose_magic_link else None)


class VerifyIn(BaseModel):
    token: str


@router.post("/verify")
def verify(payload: VerifyIn, request: Request, response: Response,
           db: Session = Depends(get_db)) -> dict:
    ip = request.client.host if request.client else None
    row = db.scalar(select(LoginToken).where(LoginToken.token_hash == hash_token(payload.token)))
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        log_auth(db, "token_invalid", row.email if row else None, ip,
                 "used" if row and row.used_at else "expired-or-unknown")
        db.commit()
        raise HTTPException(401, "This login link is invalid or has expired. Please request a new one.")

    entry = db.scalar(select(AllowedEmail).where(AllowedEmail.email == row.email))
    if entry is None or not entry.enabled:
        log_auth(db, "token_invalid", row.email, ip, "email no longer allowed")
        db.commit()
        raise HTTPException(401, "This login link is invalid or has expired. Please request a new one.")

    row.used_at = utcnow()                      # 单次使用:立即失效
    if entry.verified_at is None:
        entry.verified_at = utcnow()            # 邮箱所有权已验证

    session_raw = new_raw_token()
    db.add(UserSession(
        token_hash=hash_token(session_raw),
        email=entry.email,
        role=entry.role,
        expires_at=utcnow() + datetime.timedelta(days=settings.session_ttl_days),
    ))
    interviewer_id = None
    if entry.role != "admin":
        interviewer_id = str(resolve_interviewer(db, entry.email, entry.name).id)
    log_auth(db, "login_success", entry.email, ip)
    db.commit()

    response.set_cookie(
        SESSION_COOKIE, session_raw,
        max_age=settings.session_ttl_days * 86400,
        httponly=True, samesite="lax", secure=settings.cookie_secure, path="/",
    )
    return {"email": entry.email, "role": entry.role, "name": entry.name,
            "interviewer_id": interviewer_id}


@router.get("/me")
def me(sess: UserSession = Depends(get_session), db: Session = Depends(get_db)) -> dict:
    itv = db.scalar(select(Interviewer).where(Interviewer.email == sess.email))
    entry = db.scalar(select(AllowedEmail).where(AllowedEmail.email == sess.email))
    return {
        "email": sess.email,
        "role": sess.role,
        "name": entry.name if entry else None,
        "interviewer_id": str(itv.id) if itv else None,
        "expires_at": sess.expires_at.isoformat(),
    }


@router.post("/logout")
def logout(response: Response, sess: UserSession = Depends(get_session),
           db: Session = Depends(get_db)) -> dict:
    sess.revoked_at = utcnow()
    log_auth(db, "logout", sess.email)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"message": "logged out"}


# ---------- 白名单管理(admin) ----------

class AllowIn(BaseModel):
    email: EmailStr
    role: str = "user"
    name: str | None = None


@router.get("/allowlist")
def list_allowlist(admin: UserSession = Depends(require_admin),
                   db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AllowedEmail).order_by(AllowedEmail.added_at.desc())).all()
    return [
        {
            "id": str(r.id), "email": r.email, "name": r.name, "role": r.role,
            "enabled": r.enabled, "added_by": r.added_by,
            "added_at": r.added_at.isoformat(),
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
        }
        for r in rows
    ]


@router.post("/allowlist", status_code=201)
def add_allowlist(payload: AllowIn, admin: UserSession = Depends(require_admin),
                  db: Session = Depends(get_db)) -> dict:
    if payload.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    email = payload.email.lower().strip()
    if db.scalar(select(AllowedEmail).where(AllowedEmail.email == email)):
        raise HTTPException(409, "email already in allowlist")
    entry = AllowedEmail(email=email, role=payload.role, name=payload.name,
                         added_by=admin.email)
    db.add(entry)
    log_auth(db, "allowlist_add", email, detail=f"role={payload.role} by {admin.email}")
    db.commit()
    return {"id": str(entry.id), "email": entry.email}


class AllowPatch(BaseModel):
    enabled: bool | None = None
    role: str | None = None
    name: str | None = None


@router.patch("/allowlist/{entry_id}")
def update_allowlist(entry_id: uuid.UUID, payload: AllowPatch,
                     admin: UserSession = Depends(require_admin),
                     db: Session = Depends(get_db)) -> dict:
    entry = db.get(AllowedEmail, entry_id)
    if entry is None:
        raise HTTPException(404, "entry not found")
    changes = []
    if payload.enabled is not None and payload.enabled != entry.enabled:
        entry.enabled = payload.enabled
        changes.append(f"enabled={payload.enabled}")
        if not payload.enabled:
            _revoke_sessions(db, entry.email)   # 禁用即踢下线
    if payload.role is not None:
        if payload.role not in ROLES:
            raise HTTPException(422, f"role must be one of {ROLES}")
        entry.role = payload.role
        changes.append(f"role={payload.role}")
    if payload.name is not None:
        entry.name = payload.name
    if changes:
        log_auth(db, "allowlist_update", entry.email,
                 detail=f"{', '.join(changes)} by {admin.email}")
    db.commit()
    return {"id": str(entry.id), "enabled": entry.enabled, "role": entry.role}


@router.delete("/allowlist/{entry_id}")
def remove_allowlist(entry_id: uuid.UUID, admin: UserSession = Depends(require_admin),
                     db: Session = Depends(get_db)) -> dict:
    entry = db.get(AllowedEmail, entry_id)
    if entry is None:
        raise HTTPException(404, "entry not found")
    if entry.email == admin.email:
        raise HTTPException(409, "cannot remove yourself from the allowlist")
    _revoke_sessions(db, entry.email)
    log_auth(db, "allowlist_remove", entry.email, detail=f"by {admin.email}")
    db.delete(entry)
    db.commit()
    return {"removed": entry.email}


def _revoke_sessions(db: Session, email: str) -> None:
    for s in db.scalars(select(UserSession).where(
            UserSession.email == email, UserSession.revoked_at.is_(None))):
        s.revoked_at = utcnow()
