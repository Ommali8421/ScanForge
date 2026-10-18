"""
RQ Worker Entrypoint
Listens to designated Redis queue and dispatches reconstruction jobs.
"""

import argparse
import sys
from redis import Redis
from rq import Worker, Queue
from app.config import settings
from app.db.session import init_db
from app.utils.logging import logger


def main():
    parser = argparse.ArgumentParser(description="ScanForge RQ Worker")
    parser.add_argument(
        "--queue",
        nargs="+",
        default=[settings.active_queue],
        help="Target queue name(s) (e.g. scanforge_gpu scanforge_mock)"
    )
    args = parser.parse_args()
    queues = args.queue if isinstance(args.queue, list) else [args.queue]

    # Ensure DB tables exist
    init_db()

    logger.info(f"Starting ScanForge worker listening on queues: {queues}")
    logger.info(f"Engine mode: {settings.SCANFORGE_ENGINE}, Job timeout: {settings.SCANFORGE_JOB_TIMEOUT}s")

    try:
        redis_conn = Redis.from_url(settings.SCANFORGE_REDIS_URL)
        redis_conn.ping()
    except Exception as e:
        logger.error(f"Cannot connect to Redis at {settings.SCANFORGE_REDIS_URL}: {e}")
        sys.exit(1)

    worker = Worker(queues, connection=redis_conn, worker_ttl=settings.SCANFORGE_JOB_TIMEOUT)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
