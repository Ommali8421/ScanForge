"""
Pydantic Request & Response Schemas
Matches the API specification in docs/API.md.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class JobOptions(BaseModel):
    include_mesh: bool = False
    mesh_route: Literal["auto", "photogrammetry", "depth_fusion"] = "auto"
    poly_target: Optional[int] = None
    texture_size: int = 4096
    up_axis: Literal["y", "z"] = "y"
    units: Literal["m", "cm", "mm"] = "m"
    mask_background: bool = False
    voxel_size: Optional[float] = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    message: str


class ArtifactResponse(BaseModel):
    id: str
    job_id: str
    kind: str
    format: str
    filename: str
    size_bytes: int
    download_url: str


class JobResponse(BaseModel):
    id: str
    status: str
    scan_type: str
    quality: str
    current_stage: Optional[str] = None
    progress: int = 0
    cumulative_scale: float = 1.0
    error: Optional[str] = None
    log_tail: List[str] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)
    output_formats: List[str] = Field(default_factory=list)
    original_filename: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    artifacts: List[ArtifactResponse] = Field(default_factory=list)


class JobListResponse(BaseModel):
    total: int
    items: List[JobResponse]


class CalibrateRequest(BaseModel):
    point_a: List[float] = Field(..., description="[x, y, z] coordinates of first reference point")
    point_b: List[float] = Field(..., description="[x, y, z] coordinates of second reference point")
    real_distance: float = Field(..., gt=0.0, description="Measured real physical distance in meters")


class CalibrateResponse(BaseModel):
    status: str
    measured_distance: float
    applied_factor: float
    cumulative_scale: float


class DimensionsMeters(BaseModel):
    length: float
    width: float
    height: float


class JobReport(BaseModel):
    vertex_count: int
    face_count: int
    hole_count: int
    dimensions_meters: DimensionsMeters
    floor_area_sqm: float
    cumulative_scale: float
    up_axis: str


class CapabilitiesResponse(BaseModel):
    engine: str
    gpu_available: bool
    scan_types: List[str]
    lidar_enabled: bool
    quality_presets: List[str]
    mesh_routes: List[str]
    format_matrix: Dict[str, List[str]]
    runtime_converters: Dict[str, bool]
    limits: Dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    engine: str
    db: str
    redis: str
    disk_free_gb: float
    version: str
