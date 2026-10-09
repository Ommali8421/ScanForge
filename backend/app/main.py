"""
ScanForge FastAPI Application Entrypoint
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db.session import init_db
from app.api.health import router as health_router
from app.api.capabilities import router as capabilities_router
from app.api.jobs import router as jobs_router
from app.api.sse import router as sse_router
from app.utils.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing ScanForge database tables...")
    init_db()
    logger.info(f"ScanForge running in '{settings.SCANFORGE_ENGINE}' engine mode.")
    yield
    logger.info("ScanForge backend shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="ScanForge 3D Reconstruction Platform API",
    lifespan=lifespan
)

# CORS Configuration - Restricted to frontend origin per AGENTS.md § 10
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers under /api
app.include_router(health_router, prefix="/api")
app.include_router(capabilities_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(sse_router, prefix="/api")


@app.get("/")
def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "engine": settings.SCANFORGE_ENGINE,
        "docs": "/docs"
    }
