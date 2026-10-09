"""
Job Service
Handles Job lifecycle, status transitions, progress updates, log buffering,
and broadcasting SSE events via Redis pub/sub (with in-memory fallback).
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
from app.models.job import Job
from app.models.artifact import Artifact
from app.db.session import engine
from app.utils.logging import logger
from app.config import settings

Tuple_JobList = tuple[int, List[Job]]

# Memory pub/sub fallback for local environments without running Redis
_memory_listeners: Dict[str, List[Any]] = {}



def broadcast_event(job_id: str, event_type: str, data: dict):
    """Publish an SSE event to Redis channel and in-memory listeners."""
    payload = json.dumps({"type": event_type, "data": data})

    # Try publishing to Redis
    try:
        import redis
        r = redis.Redis.from_url(settings.SCANFORGE_REDIS_URL)
        r.publish(f"job:{job_id}", payload)
    except Exception:
        pass

    # In-memory listeners dispatch
    listeners = _memory_listeners.get(job_id, [])
    for queue in list(listeners):
        try:
            queue.put_nowait((event_type, data))
        except Exception:
            pass


def create_job(
    scan_type: str,
    quality: str,
    output_formats: List[str],
    options: Dict[str, Any],
    original_filename: str,
    input_file_path: str
) -> Job:
    """Create and persist a new Job."""
    with Session(engine) as session:
        job = Job(
            scan_type=scan_type,
            quality=quality,
            output_formats=output_formats,
            options=options,
            original_filename=original_filename,
            input_file_path=input_file_path,
            status="queued",
            progress=0,
            cumulative_scale=1.0,
            log_tail=["[System] Job created and enqueued."]
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def get_job(job_id: str) -> Optional[Job]:
    """Retrieve job by ID."""
    with Session(engine) as session:
        return session.get(Job, job_id)


def list_jobs(limit: int = 20, offset: int = 0, status: Optional[str] = None) -> Tuple_JobList:
    """List jobs with pagination and optional status filter."""
    with Session(engine) as session:
        query = select(Job).order_by(Job.created_at.desc())
        if status:
            query = query.where(Job.status == status)
        
        all_items = session.exec(query).all()
        total = len(all_items)
        items = all_items[offset : offset + limit]
        return total, items


def update_job_progress(job_id: str, stage: str, progress: int, message: str = ""):
    """Update job stage and percentage progress, appending log and broadcasting."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        
        job.current_stage = stage
        job.progress = max(0, min(100, progress))
        if job.status in {"queued", "preprocessing"}:
            job.status = "running"
            if not job.started_at:
                job.started_at = datetime.now(timezone.utc)

        log_msg = f"[{stage}] ({progress}%) {message}" if message else f"[{stage}] Progress: {progress}%"
        # Keep recent 200 log lines
        tail = list(job.log_tail or [])
        tail.append(log_msg)
        job.log_tail = tail[-200:]

        session.add(job)
        session.commit()

    broadcast_event(job_id, "stage", {
        "stage": stage,
        "progress": progress,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    broadcast_event(job_id, "log", {
        "line": log_msg,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


def append_job_log(job_id: str, line: str):
    """Append a log line to job history and broadcast to listeners."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        tail = list(job.log_tail or [])
        tail.append(line)
        job.log_tail = tail[-200:]
        session.add(job)
        session.commit()

    broadcast_event(job_id, "log", {
        "line": line,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


def set_job_completed(job_id: str):
    """Mark job as completed."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.status = "completed"
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        tail = list(job.log_tail or [])
        tail.append("[System] Job completed successfully.")
        job.log_tail = tail[-200:]
        session.add(job)
        session.commit()

    broadcast_event(job_id, "completed", {"job_id": job_id, "status": "completed"})


def set_job_failed(job_id: str, error_message: str):
    """Mark job as failed."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.status = "failed"
        job.error = error_message
        job.completed_at = datetime.now(timezone.utc)
        tail = list(job.log_tail or [])
        tail.append(f"[Error] {error_message}")
        job.log_tail = tail[-200:]
        session.add(job)
        session.commit()

    broadcast_event(job_id, "error", {"job_id": job_id, "status": "failed", "error": error_message})


def set_job_cancelled(job_id: str):
    """Mark job as cancelled."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        tail = list(job.log_tail or [])
        tail.append("[System] Job cancelled by user.")
        job.log_tail = tail[-200:]
        session.add(job)
        session.commit()

    broadcast_event(job_id, "cancelled", {"job_id": job_id, "status": "cancelled"})


def add_artifact(job_id: str, kind: str, format_name: str, filename: str, size_bytes: int, file_path: str) -> Artifact:
    """Register a generated artifact in the database."""
    with Session(engine) as session:
        art = Artifact(
            job_id=job_id,
            kind=kind,
            format=format_name,
            filename=filename,
            size_bytes=size_bytes,
            file_path=file_path
        )
        session.add(art)
        session.commit()
        session.refresh(art)
        return art


def get_job_artifacts(job_id: str) -> List[Artifact]:
    """Retrieve all artifacts associated with a job."""
    with Session(engine) as session:
        return session.exec(select(Artifact).where(Artifact.job_id == job_id)).all()


# Helper type for list_jobs
Tuple_JobList = tuple[int, List[Job]]
