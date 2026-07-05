from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import settings
from .routers.analytics import router as analytics_router
from .routers.applications import router as applications_router
from .routers.auth import router as auth_router
from .routers.booking import router as booking_router
from .routers.dev import router as dev_router
from .routers.emails import router as emails_router
from .routers.jobs import router as jobs_router
from .routers.slots import interviewer_router, router as slots_router
from .scheduler import shutdown_scheduler, start_scheduler


def _bootstrap_admin() -> None:
    """白名单为空时写入初始 admin(来自 ADMIN_EMAIL),否则谁都登不进。"""
    if not settings.admin_email:
        return
    from sqlalchemy import select

    from .database import SessionLocal
    from .models import AllowedEmail

    db = SessionLocal()
    try:
        email = settings.admin_email.lower().strip()
        exists = db.scalar(select(AllowedEmail).where(AllowedEmail.email == email))
        if exists is None:
            db.add(AllowedEmail(email=email, role="admin", enabled=True,
                                added_by="bootstrap"))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap_admin()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="HAS API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(slots_router, prefix="/api")
app.include_router(interviewer_router, prefix="/api")
app.include_router(applications_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(emails_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(booking_router, prefix="/api")
app.include_router(dev_router, prefix="/api")  # dev only — remove before production


@app.get("/")
def root() -> dict:
    return {"service": "HAS API", "docs": "/docs"}
