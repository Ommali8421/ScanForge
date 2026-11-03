"""
Job Cleanup Service
Periodically removes jobs and associated artifacts older than SCANFORGE_JOB_TTL_DAYS.
"""

from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select
from app.models.job import Job
from app.db.session import engine
from app.services.storage import storage_service
from app.config import settings
from app.utils.logging import logger


def cleanup_expired_jobs() -> int:
    """Delete jobs older than TTL and return the number of deleted records."""
    ttl_days = settings.SCANFORGE_JOB_TTL_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)

    deleted_count = 0
    with Session(engine) as session:
        expired = session.exec(select(Job).where(Job.created_at < cutoff)).all()
        for job in expired:
            try:
                storage_service.delete_job_files(job.id)
                session.delete(job)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed deleting expired job {job.id}: {e}")

        session.commit()

    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} jobs older than {ttl_days} days.")
    return deleted_count


def cleanup_job_scratch_files(job_id: str) -> int:
    """
    Safely purges heavy intermediate scratch files (raw depth maps, dense point clouds,
    and intermediate checkpoint shards) for a completed job, freeing >80% disk space while
    strictly preserving deliverables:
      - mesh.glb, mesh.ply, mesh.fbx, mesh.obj, mesh.stl, mesh.usdz, mesh_obj.zip
      - model.splat, cleaned_splat.ply, splat.zip
      - floor_plan.svg, floor_plan.png
      - quality_report.json, room_analysis.json, pipeline.log
      - sparse_txt/, preview_textured.glb
    Returns the total bytes reclaimed.
    """
    workdir = storage_service.get_job_workdir(job_id)
    if not workdir.exists():
        return 0

    reclaimed_bytes = 0

    # 1. Purge intermediate depth directories
    for dir_name in ["depth_raw", "depth_aligned"]:
        dpath = workdir / dir_name
        if dpath.exists() and dpath.is_dir():
            try:
                import shutil
                size = sum(f.stat().st_size for f in dpath.glob("**/*") if f.is_file())
                shutil.rmtree(dpath)
                reclaimed_bytes += size
                logger.info(f"[Cleanup] Purged scratch directory {dir_name}/ ({size:,} bytes) for job {job_id}.")
            except Exception as e:
                logger.warning(f"[Cleanup] Could not remove {dir_name}: {e}")

    # 2. Purge heavy intermediate scratch files
    scratch_files = [
        "mesh_dense.ply",
        "mesh_tsdf_raw.ply",
        "mesh_splat_raw.ply",
        "mesh_repaired.ply",
        "mesh_cleaned.ply",
        "scene.mvs",
        "scene_textured.mvs",
    ]
    for sf in scratch_files:
        fpath = workdir / sf
        if fpath.exists() and fpath.is_file():
            try:
                size = fpath.stat().st_size
                fpath.unlink()
                reclaimed_bytes += size
            except Exception as e:
                logger.warning(f"[Cleanup] Could not remove scratch file {sf}: {e}")

    # 3. Purge intermediate .dmap files
    for dmap in workdir.glob("*.dmap"):
        try:
            size = dmap.stat().st_size
            dmap.unlink()
            reclaimed_bytes += size
        except Exception:
            pass

    logger.info(f"[Cleanup] Job {job_id}: reclaimed {reclaimed_bytes / (1024 * 1024):.2f} MB scratch space.")
    return reclaimed_bytes
