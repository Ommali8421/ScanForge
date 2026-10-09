"""
Health Check API Route
"""

import shutil
from fastapi import APIRouter
from redis import Redis
from sqlmodel import Session, text
from app.config import settings
from app.db.session import engine
from app.models.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["system"])


@router.get("", response_model=HealthResponse)
def get_health():
    # Test DB
    db_status = "connected"
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Test Redis
    redis_status = "connected"
    try:
        r = Redis.from_url(settings.SCANFORGE_REDIS_URL, socket_connect_timeout=1)
        r.ping()
    except Exception:
        redis_status = "disconnected"

    # Disk space
    try:
        _, _, free = shutil.disk_usage(settings.data_path)
        disk_free_gb = round(free / (1024 ** 3), 1)
    except Exception:
        disk_free_gb = 0.0

    overall = "ok" if db_status == "connected" else "degraded"

    return HealthResponse(
        status=overall,
        engine=settings.SCANFORGE_ENGINE,
        db=db_status,
        redis=redis_status,
        disk_free_gb=disk_free_gb,
        version=settings.VERSION
    )
