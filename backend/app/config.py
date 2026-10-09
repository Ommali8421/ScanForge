"""
ScanForge Configuration Module
Loads application configuration from environment variables with Pydantic Settings.
"""

from pathlib import Path
from typing import List, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General & Engine
    PROJECT_NAME: str = "ScanForge"
    VERSION: str = "0.1.0"
    SCANFORGE_ENGINE: Literal["mock", "real"] = "mock"
    DEBUG: bool = False

    # Database & Redis
    SCANFORGE_DB_URL: str = "sqlite:////data/scanforge.db"
    SCANFORGE_REDIS_URL: str = "redis://localhost:6379/0"

    # Queues (separate queues for mock vs gpu workers)
    SCANFORGE_QUEUE_MOCK: str = "scanforge_mock"
    SCANFORGE_QUEUE_GPU: str = "scanforge_gpu"

    # Storage Paths
    SCANFORGE_DATA_DIR: str = "/data"

    # Network & Security
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

    # Uploads & Limits
    SCANFORGE_MAX_UPLOAD_MB: int = 2048
    SCANFORGE_MAX_VIDEO_SECONDS: int = 180
    SCANFORGE_MAX_FRAMES_PHOTO: int = 300
    SCANFORGE_MAX_FRAMES_3DGS: int = 300

    # Job Execution & Timeouts
    SCANFORGE_CONCURRENCY: int = 1
    SCANFORGE_STAGE_TIMEOUT: int = 7200  # 2 hours per stage
    SCANFORGE_JOB_TIMEOUT: int = 21600   # 6 hours minimum per job
    SCANFORGE_JOB_TTL_DAYS: int = 30

    # Feature Flags
    ENABLE_LIDAR: bool = False

    @property
    def data_path(self) -> Path:
        p = Path(self.SCANFORGE_DATA_DIR)
        # Fallback to local data folder if /data is not mounted or not writable
        if not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                p = Path.cwd() / "data"
                p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def uploads_path(self) -> Path:
        p = self.data_path / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def jobs_path(self) -> Path:
        p = self.data_path / "jobs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def active_queue(self) -> str:
        return self.SCANFORGE_QUEUE_MOCK if self.SCANFORGE_ENGINE == "mock" else self.SCANFORGE_QUEUE_GPU


settings = Settings()
