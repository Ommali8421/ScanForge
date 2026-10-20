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

    # Full unredacted execution log file
    full_log_path = workdir / "pipeline.log"
    full_log_file = open(full_log_path, "a", encoding="utf-8")

    import re
    # Patterns for filtering out verbose Ceres solver iteration tables from live stream
    ceres_header_pattern = re.compile(r"Iter\s+Cost\s+Cost change", re.IGNORECASE)
    ceres_row_pattern = re.compile(r"^\s*\d+\s+[0-9.eE+-]+\s+[0-9.eE+-]+\s+[0-9.eE+-]+")

    def progress_callback(stage_name: str, pct: int, msg: str):
        update_job_progress(job_id, stage_name, pct, msg)

    def log_callback(line: str):
        clean_line = line.rstrip()
        # 1. Always append unredacted line to full disk log
        try:
            full_log_file.write(clean_line + "\n")
            full_log_file.flush()
        except Exception:
            pass

        # 2. Filter out Ceres solver iteration tables from live SSE and job.log_tail
        if ceres_header_pattern.search(clean_line) or ceres_row_pattern.match(clean_line):
            return

        append_job_log(job_id, clean_line)

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
                            elif suffix in ("json", "txt", "log"):
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

            # Ensure pipeline.log is registered as an artifact
            if full_log_path.exists():
                dest_log = art_dir / "pipeline.log"
                if dest_log.resolve() != full_log_path.resolve():
                    shutil.copy2(full_log_path, dest_log)
                add_artifact(
                    job_id=job_id,
                    kind="report",
                    format_name="txt",
                    filename="pipeline.log",
                    size_bytes=dest_log.stat().st_size,
                    file_path=str(dest_log)
                )

            storage_service.create_zip_archive(job_id)
            set_job_completed(job_id)

    except Exception as e:
        logger.exception(f"Job {job_id} failed during execution: {e}")
        # Even on failure, register full pipeline.log and diagnostic artifacts if present
        try:
            art_dir = storage_service.get_job_artifacts_dir(job_id)
            workdir = storage_service.get_job_workdir(job_id)

            # Register pipeline.log
            if full_log_path.exists():
                dest_log = art_dir / "pipeline.log"
                if dest_log.resolve() != full_log_path.resolve():
                    shutil.copy2(full_log_path, dest_log)
                add_artifact(
                    job_id=job_id,
                    kind="report",
                    format_name="txt",
                    filename="pipeline.log",
                    size_bytes=dest_log.stat().st_size,
                    file_path=str(dest_log)
                )

            # Register diagnostic files from workdir if they were created before failure
            diag_items = [
                ("camera_path.png", "image", "png"),
                ("sfm_report.json", "report", "json"),
                ("sparse.ply", "pointcloud", "ply"),
                ("cuts", "image", "dir"),
            ]
            for item_name, kind, fmt in diag_items:
                item_src = workdir / item_name
                if item_src.exists():
                    item_dest = art_dir / item_name
                    if item_src.is_dir():
                        if item_dest.resolve() != item_src.resolve():
                            shutil.copytree(item_src, item_dest, dirs_exist_ok=True)
                        dir_size = sum(f.stat().st_size for f in item_dest.glob("**/*") if f.is_file())
                        add_artifact(job_id, kind, fmt, item_name, dir_size, str(item_dest))
                    else:
                        if item_dest.resolve() != item_src.resolve():
                            shutil.copy2(item_src, item_dest)
                        add_artifact(job_id, kind, fmt, item_name, item_dest.stat().st_size, str(item_dest))
        except Exception as err:
            logger.warning(f"Failed registering diagnostic artifacts for failed job {job_id}: {err}")

        if cancel_token.is_cancelled():
            set_job_cancelled(job_id)
        else:
            set_job_failed(job_id, str(e))
    finally:
        active_cancel_tokens.pop(job_id, None)
        try:
            full_log_file.close()
        except Exception:
            pass
