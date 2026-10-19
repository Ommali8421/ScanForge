"""
Queue Pipeline Task
Executes reconstruction pipeline stages in background worker.
"""

import shutil
from pathlib import Path
from typing import Dict
from app.pipelines.base import JobContext, CancelToken
from app.pipelines.registry import pipeline_registry
from app.services.storage import storage_service
from app.services.job_service import (
    get_job,
    update_job_progress,
    append_job_log,
    add_artifact,
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
        stage_results = pipeline.run(ctx)

        if cancel_token.is_cancelled():
            set_job_cancelled(job_id)
        else:
            # Register output artifacts from pipeline stages (Portability Rule 3: stage isolation)
            art_dir = storage_service.get_job_artifacts_dir(job_id)
            for res in stage_results or []:
                for out_file in res.output_files:
                    if out_file.exists():
                        dest_file = art_dir / out_file.name
                        if out_file.is_dir():
                            if dest_file.resolve() != out_file.resolve():
                                shutil.copytree(out_file, dest_file, dirs_exist_ok=True)
                            dir_size = sum(f.stat().st_size for f in dest_file.glob("**/*") if f.is_file())
                            add_artifact(
                                job_id=job_id,
                                kind="archive" if out_file.name == "frames" else "model",
                                format_name="dir",
                                filename=out_file.name,
                                size_bytes=dir_size,
                                file_path=str(dest_file)
                            )
                        else:
                            if dest_file.resolve() != out_file.resolve():
                                shutil.copy2(out_file, dest_file)

                            suffix = out_file.suffix.lower().lstrip(".")
                            kind = "model"
                            if suffix in ("ply", "xyz", "las"):
                                kind = "pointcloud"
                            elif suffix in ("png", "jpg", "jpeg", "webp"):
                                kind = "image"
                            elif suffix in ("json", "txt"):
                                kind = "report"
                            elif suffix in ("splat",):
                                kind = "splat"
                            elif suffix in ("glb", "obj", "fbx", "stl", "usdz"):
                                kind = "mesh"

                            add_artifact(
                                job_id=job_id,
                                kind=kind,
                                format_name=suffix,
                                filename=out_file.name,
                                size_bytes=dest_file.stat().st_size,
                                file_path=str(dest_file)
                            )

            storage_service.create_zip_archive(job_id)
            set_job_completed(job_id)

    except Exception as e:
        logger.exception(f"Job {job_id} failed during execution: {e}")
        if cancel_token.is_cancelled():
            set_job_cancelled(job_id)
        else:
            set_job_failed(job_id, str(e))
    finally:
        active_cancel_tokens.pop(job_id, None)
