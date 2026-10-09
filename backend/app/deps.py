"""
Dependency Injection Providers
"""

import threading
from typing import Generator
from redis import Redis
from rq import Queue
from sqlmodel import Session
from app.config import settings
from app.db.session import engine
from app.queue.tasks import run_pipeline_task
from app.utils.logging import logger


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def enqueue_job(job_id: str):
    """Dispatch job to active RQ queue or fallback background thread if Redis is offline."""
    try:
        redis_conn = Redis.from_url(settings.SCANFORGE_REDIS_URL, socket_connect_timeout=1)
        redis_conn.ping()
        q = Queue(settings.active_queue, connection=redis_conn)
        q.enqueue(
            run_pipeline_task,
            job_id,
            job_timeout=settings.SCANFORGE_JOB_TIMEOUT,
            result_ttl=86400
        )
        logger.info(f"Enqueued job {job_id} to RQ queue '{settings.active_queue}'")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}); running job {job_id} in background thread fallback.")
        t = threading.Thread(target=run_pipeline_task, args=(job_id,), daemon=True)
        t.start()
