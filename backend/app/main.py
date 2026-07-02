from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import settings
from .routers.applications import router as applications_router
from .routers.booking import router as booking_router
from .routers.dev import router as dev_router
from .routers.slots import interviewer_router, router as slots_router
from .scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(slots_router, prefix="/api")
app.include_router(interviewer_router, prefix="/api")
app.include_router(applications_router, prefix="/api")
app.include_router(booking_router, prefix="/api")
app.include_router(dev_router, prefix="/api")  # dev only — remove before production


@app.get("/")
def root() -> dict:
    return {"service": "HAS API", "docs": "/docs"}
