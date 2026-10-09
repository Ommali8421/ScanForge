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
