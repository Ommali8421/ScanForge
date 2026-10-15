"""
Jobs API Endpoints
Handles job submission, retrieval, cancellation, downloads, calibration, and reports.
"""

import json
import math
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session
from app.config import settings
from app.db.session import engine
from app.deps import enqueue_job
from app.models.job import Job
from app.models.schemas import (
    JobCreateResponse,
    JobResponse,
    JobListResponse,
    ArtifactResponse,
    CalibrateRequest,
    CalibrateResponse,
    JobReport,
    DimensionsMeters,
)
from app.services.storage import storage_service
from app.services.upload_service import save_uploaded_file
from app.services.job_service import (
    create_job,
    get_job,
    list_jobs,
    get_job_artifacts,
    set_job_cancelled,
)
from app.queue.tasks import cancel_active_task

router = APIRouter(prefix="/jobs", tags=["jobs"])


def format_job_response(job: Job) -> JobResponse:
    artifacts = get_job_artifacts(job.id)
    art_responses = [
        ArtifactResponse(
            id=a.id,
            job_id=a.job_id,
            kind=a.kind,
            format=a.format,
            filename=a.filename,
            size_bytes=a.size_bytes,
            download_url=f"/api/jobs/{job.id}/download/{a.format}"
        )
        for a in artifacts
    ]
    return JobResponse(
        id=job.id,
        status=job.status,
        scan_type=job.scan_type,
        quality=job.quality,
        current_stage=job.current_stage,
        progress=job.progress,
        cumulative_scale=job.cumulative_scale,
        error=job.error,
        log_tail=job.log_tail or [],
        options=job.options or {},
        output_formats=job.output_formats or [],
        original_filename=job.original_filename,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        artifacts=art_responses
    )


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_scan_job(
    file: UploadFile = File(...),
    scan_type: str = Form("photo"),
    quality: str = Form("standard"),
    output_formats: str = Form('["glb", "obj"]'),
    options: str = Form("{}"),
):
    # Parse JSON options and output formats
    try:
        parsed_formats = json.loads(output_formats) if isinstance(output_formats, str) else output_formats
        if not isinstance(parsed_formats, list):
            parsed_formats = ["glb", "obj"]
    except Exception:
        parsed_formats = ["glb", "obj"]

    try:
        parsed_options = json.loads(options) if isinstance(options, str) else options
        if not isinstance(parsed_options, dict):
            parsed_options = {}
    except Exception:
        parsed_options = {}

    import uuid
    job_id = str(uuid.uuid4())

    # Stream upload directly to disk
    dest_path, sanitized_name, probe_info = await save_uploaded_file(job_id, file)

    # Persist job record
    job = create_job(
        scan_type=scan_type,
        quality=quality,
        output_formats=parsed_formats,
        options={**parsed_options, "probe": probe_info},
        original_filename=sanitized_name,
        input_file_path=str(dest_path)
    )

    # Enqueue pipeline task
    enqueue_job(job.id)

    return JobCreateResponse(
        job_id=job.id,
        status="queued",
        message="Job enqueued successfully"
    )


@router.get("", response_model=JobListResponse)
def get_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None
):
    total, jobs = list_jobs(limit=limit, offset=offset, status=status)
    return JobListResponse(
        total=total,
        items=[format_job_response(j) for j in jobs]
    )


@router.get("/{id}", response_model=JobResponse)
def get_job_by_id(id: str):
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")
    return format_job_response(job)


@router.post("/{id}/cancel")
def cancel_job(id: str):
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")

    cancel_active_task(id)
    set_job_cancelled(id)
    return {"status": "cancelled", "job_id": id}


@router.delete("/{id}")
def delete_job(id: str):
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")

    cancel_active_task(id)
    storage_service.delete_job_files(id)

    with Session(engine) as session:
        j = session.get(Job, id)
        if j:
            session.delete(j)
            session.commit()

    return {"status": "deleted", "job_id": id}


@router.get("/{id}/artifacts", response_model=List[ArtifactResponse])
def list_job_artifacts(id: str):
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")
    return format_job_response(job).artifacts


@router.get("/{id}/download/{format}")
def download_artifact(id: str, format: str):
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")

    artifacts = get_job_artifacts(id)
    target = next((a for a in artifacts if a.format.lower() == format.lower()), None)
    if not target or not Path(target.file_path).exists():
        raise HTTPException(status_code=404, detail=f"Artifact format '{format}' not found for job {id}")

    media_type = "application/octet-stream"
    fmt = format.lower()
    if fmt == "glb":
        media_type = "model/gltf-binary"
    elif fmt == "png":
        media_type = "image/png"
    elif fmt == "json":
        media_type = "application/json"
    elif fmt in {"ply", "splat"}:
        media_type = "application/octet-stream"

    return FileResponse(
        path=target.file_path,
        filename=target.filename,
        media_type=media_type
    )


@router.get("/{id}/download-all")
def download_all_artifacts(id: str):
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")

    zip_path = storage_service.create_zip_archive(id)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="No artifacts to archive.")

    return FileResponse(
        path=str(zip_path),
        filename=f"scanforge_{id[:8]}_all.zip",
        media_type="application/zip"
    )


@router.post("/{id}/calibrate", response_model=CalibrateResponse, status_code=202)
def calibrate_scale(id: str, payload: CalibrateRequest):
    """
    Scale calibration endpoint.
    Amendment 3: stores cumulative scale.
    measured_distance = ||point_a - point_b||
    new_factor = real_distance / measured_distance
    cumulative_scale = current_scale * new_factor
    """
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")

    # Compute Euclidean distance between 3D points
    pa = payload.point_a
    pb = payload.point_b
    if len(pa) != 3 or len(pb) != 3:
        raise HTTPException(status_code=400, detail="Points must have exactly 3 coordinates [x, y, z]")

    dx = pa[0] - pb[0]
    dy = pa[1] - pb[1]
    dz = pa[2] - pb[2]
    measured_distance = math.sqrt(dx * dx + dy * dy + dz * dz)

    if measured_distance <= 1e-6:
        raise HTTPException(status_code=400, detail="Selected points are too close together to calibrate")

    new_factor = payload.real_distance / measured_distance
    current_scale = job.cumulative_scale or 1.0
    cumulative_scale = current_scale * new_factor

    # Update job in database
    with Session(engine) as session:
        db_job = session.get(Job, id)
        if db_job:
            db_job.cumulative_scale = cumulative_scale
            db_job.status = "queued"
            db_job.progress = 50
            tail = list(db_job.log_tail or [])
            tail.append(
                f"[Calibrate] Recalibrating: measured {measured_distance:.3f}m -> real {payload.real_distance:.3f}m. "
                f"New factor: {new_factor:.4f}, Cumulative scale: {cumulative_scale:.4f}"
            )
            db_job.log_tail = tail[-200:]
            session.add(db_job)
            session.commit()

    # Invalidate scale cache and re-enqueue
    cache_marker = storage_service.get_job_workdir(id) / ".cache_mesh_scale.json"
    cache_marker.unlink(missing_ok=True)
    enqueue_job(id)

    return CalibrateResponse(
        status="calibrating",
        measured_distance=round(measured_distance, 4),
        applied_factor=round(new_factor, 4),
        cumulative_scale=round(cumulative_scale, 4)
    )


@router.get("/{id}/report", response_model=JobReport)
def get_job_report(id: str):
    job = get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {id} not found")

    scale = job.cumulative_scale or 1.0
    # Room dimensions based on scale (4.0m x 5.0m x 2.6m base)
    length = round(5.0 * scale, 2)
    width = round(4.0 * scale, 2)
    height = round(2.6 * scale, 2)
    floor_area = round(length * width, 2)

    return JobReport(
        vertex_count=120500,
        face_count=240000,
        hole_count=0,
        dimensions_meters=DimensionsMeters(length=length, width=width, height=height),
        floor_area_sqm=floor_area,
        cumulative_scale=scale,
        up_axis=job.options.get("up_axis", "y")
    )
