"""
Job Database Model
Defines the Job table schema using SQLModel.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON
import uuid


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    status: str = Field(default="queued", index=True)  # queued, preprocessing, running, exporting, completed, failed, cancelled
    scan_type: str = Field(default="photo", index=True)  # photo, gaussian_splat, lidar
    quality: str = Field(default="standard")  # draft, standard, high
    current_stage: Optional[str] = Field(default=None)
    progress: int = Field(default=0)  # 0 to 100
    cumulative_scale: float = Field(default=1.0)  # Cumulative scale factor

    error: Optional[str] = Field(default=None)
    log_tail: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    options: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    output_formats: List[str] = Field(default_factory=lambda: ["glb", "obj"], sa_column=Column(JSON))

    original_filename: Optional[str] = Field(default=None)
    input_file_path: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
