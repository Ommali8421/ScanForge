"""
Artifact Database Model
Defines the Artifact table schema using SQLModel.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
import uuid


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    job_id: str = Field(index=True)
    kind: str = Field(default="mesh")  # mesh, splat, report, pointcloud, archive
    format: str = Field(default="glb")  # glb, obj, ply, splat, stl, xyz, zip, json
    filename: str = Field(default="")
    size_bytes: int = Field(default=0)
    file_path: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
