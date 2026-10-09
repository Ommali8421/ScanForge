"""
Queue Pipeline Task
Executes reconstruction pipeline stages in background worker.
"""

from pathlib import Path
from typing import Dict
from app.pipelines.base import JobContext, CancelToken
from app.pipelines.registry import pipeline_registry
from app.services.storage import storage_service
from app.services.job_service import (
    get_job,
    update_job_progress,
    append_job_log,
    set_job_completed,
    set_job_failed,
    set_job_cancelled
)
from app.utils.logging import logger

# Active cancel tokens by job_id
active_cancel_tokens: Dict[str, CancelToken] = {}


def cancel_active_task(job_id: str) -> bool:
    """Trigger cancel token for a running job."""
    token = active_cancel_tokens.get(job_id)
    if token:
        token.cancel()
        return True
    return False


def run_pipeline_task(job_id: str):
    """Main worker task executing reconstruction pipeline."""
    job = get_job(job_id)
    if not job:
        logger.error(f"Cannot execute task: Job {job_id} not found.")
        return

    workdir = storage_service.get_job_workdir(job_id)
    cancel_token = CancelToken()
    active_cancel_tokens[job_id] = cancel_token

    def progress_callback(stage_name: str, pct: int, msg: str):
        update_job_progress(job_id, stage_name, pct, msg)

    def log_callback(line: str):
        append_job_log(job_id, line)

    ctx = JobContext(
        job_id=job_id,
        workdir=workdir,
        params={
            "scan_type": job.scan_type,
            "quality": job.quality,
            "options": job.options,
            "output_formats": job.output_formats,
            "input_file_path": job.input_file_path
        },
        cancel_token=cancel_token,
        progress_cb=progress_callback,
        log_cb=log_callback,
        cumulative_scale=job.cumulative_scale
    )

    try:
        pipeline = pipeline_registry.get_pipeline(job.scan_type)
        pipeline.run(ctx)

        if cancel_token.is_cancelled():
            set_job_cancelled(job_id)
        else:
            set_job_completed(job_id)

    except Exception as e:
        logger.exception(f"Job {job_id} failed during execution: {e}")
        if cancel_token.is_cancelled():
            set_job_cancelled(job_id)
        else:
            set_job_failed(job_id, str(e))
    finally:
        active_cancel_tokens.pop(job_id, None)
