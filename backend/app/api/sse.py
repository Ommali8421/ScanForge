"""
Server-Sent Events (SSE) Streaming Route
Streams live job stages and logs, replaying current stage and log history upon connection.
"""

import asyncio
import json
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.services.job_service import get_job, _memory_listeners
from app.config import settings

router = APIRouter(prefix="/jobs", tags=["sse"])


async def event_generator(job_id: str, request: Request) -> AsyncGenerator[str, None]:
    job = get_job(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return

    # Amendment 6: Replay current stage, progress, and recent log lines on connect
    stage_event = {
        "stage": job.current_stage or "queued",
        "progress": job.progress,
        "status": job.status
    }
    yield f"event: stage\ndata: {json.dumps(stage_event)}\n\n"

    # Replay log tail
    if job.log_tail:
        for line in job.log_tail:
            yield f"event: log\ndata: {json.dumps({'line': line})}\n\n"

    # If job has already terminated, send termination event and exit
    if job.status in {"completed", "failed", "cancelled"}:
        yield f"event: {job.status}\ndata: {json.dumps({'job_id': job_id, 'status': job.status})}\n\n"
        return

    # Set up listener queue for live streaming
    listener_queue: asyncio.Queue = asyncio.Queue()
    _memory_listeners.setdefault(job_id, []).append(listener_queue)

    # Redis pubsub listener for cross-container worker events
    redis_client = None
    pubsub = None
    redis_task = None

    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.SCANFORGE_REDIS_URL)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"job:{job_id}")

        async def redis_reader():
            try:
                async for message in pubsub.listen():
                    if message and message.get("type") == "message":
                        raw_data = message.get("data")
                        if isinstance(raw_data, bytes):
                            raw_data = raw_data.decode("utf-8")
                        parsed = json.loads(raw_data)
                        ev_type = parsed.get("type")
                        ev_data = parsed.get("data", {})
                        await listener_queue.put((ev_type, ev_data))
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        redis_task = asyncio.create_task(redis_reader())
    except Exception:
        pass

    try:
        while True:
            # Check client disconnection
            if await request.is_disconnected():
                break

            try:
                # Wait for next event with a timeout for keepalive
                event_type, data = await asyncio.wait_for(listener_queue.get(), timeout=15.0)
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

                if event_type in {"completed", "failed", "cancelled"}:
                    break
            except asyncio.TimeoutError:
                # Keepalive comment
                yield ": keepalive\n\n"

    finally:
        # Cleanup Redis pubsub reader
        if redis_task:
            redis_task.cancel()
            try:
                await redis_task
            except asyncio.CancelledError:
                pass

        if pubsub:
            try:
                await pubsub.unsubscribe(f"job:{job_id}")
                await pubsub.aclose()
            except Exception:
                pass

        if redis_client:
            try:
                await redis_client.aclose()
            except Exception:
                pass

        # Cleanup in-memory listener queue
        if job_id in _memory_listeners and listener_queue in _memory_listeners[job_id]:
            _memory_listeners[job_id].remove(listener_queue)


@router.get("/{id}/events")
async def stream_job_events(id: str, request: Request):
    """Subscribe to SSE event stream for a specific reconstruction job."""
    return StreamingResponse(
        event_generator(id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
