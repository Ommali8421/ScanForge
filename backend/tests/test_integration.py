"""
Integration tests for:
1. SSE streaming & replay of current stage + recent log lines on connect
2. Cancellation ensuring the external child process is actually killed
3. Upload size cap enforcement (HTTP 413) and disk cleanup
"""

import io
import os
import signal
import time
import threading
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.pipelines.base import CancelToken
from app.pipelines.tool_runner import ToolRunner
from app.services.job_service import (
    create_job,
    update_job_progress,
    append_job_log,
    set_job_completed,
    get_job,
)
from app.services.storage import storage_service

client = TestClient(app)


def test_sse_replay_on_connect():
    """Verify SSE replays current stage, progress, and recent log lines on initial connection."""
    # Create test job
    job = create_job(
        scan_type="photo",
        quality="standard",
        output_formats=["glb"],
        options={},
        original_filename="test_scene.mp4",
        input_file_path="/tmp/test_scene.mp4"
    )
    job_id = job.id

    # Simulate ongoing progress and log history before SSE connection
    update_job_progress(job_id, "sparse_sfm", 35, "SfM feature matching in progress")
    append_job_log(job_id, "[SfM] Extracted 1200 features")
    append_job_log(job_id, "[SfM] Sequential match registered 48 cameras")
    set_job_completed(job_id)

    # Connect to SSE endpoint
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        content = ""
        for chunk in response.iter_text():
            content += chunk

        # Check stage event replay
        assert "event: stage" in content
        assert "sparse_sfm" in content
        assert '"progress": 100' in content or '"progress": 35' in content or "completed" in content

        # Check log line replay
        assert "event: log" in content
        assert "[SfM] Extracted 1200 features" in content
        assert "[SfM] Sequential match registered 48 cameras" in content

        # Check final status event
        assert "event: completed" in content


def test_cancel_kills_child_process():
    """Verify that cancelling a job kills the spawned child process tree."""
    cancel_token = CancelToken()
    child_pid = None
    runner_error = None
    runner_finished = threading.Event()

    def run_tool():
        nonlocal runner_error
        try:
            # Run a sleep process that lasts 30 seconds
            ToolRunner.run(
                ["sleep", "30"],
                timeout=30,
                cancel_token=cancel_token
            )
        except Exception as e:
            runner_error = e
        finally:
            runner_finished.set()

    thread = threading.Thread(target=run_tool, daemon=True)
    thread.start()

    # Wait for process to start and register PID
    for _ in range(50):
        child_pid = cancel_token.get_active_pid()
        if child_pid is not None:
            break
        time.sleep(0.05)

    assert child_pid is not None, "Child process was not launched or PID was not captured."

    # Verify process is actively running
    try:
        os.kill(child_pid, 0)
        is_running = True
    except OSError:
        is_running = False
    assert is_running, f"Child PID {child_pid} should be running before cancellation."

    # Cancel job
    cancel_token.cancel()

    # Wait for ToolRunner to handle cancellation
    runner_finished.wait(timeout=5.0)

    # Assert ToolRunner raised cancellation error
    assert runner_error is not None
    assert "cancellation" in str(runner_error).lower()

    # Wait briefly for OS process cleanup
    time.sleep(0.2)

    # Verify child process is dead
    process_alive = True
    try:
        os.kill(child_pid, 0)
    except OSError:
        process_alive = False

    assert not process_alive, f"Child PID {child_pid} was not terminated after cancellation."


def test_upload_size_cap_enforcement(monkeypatch, tmp_path):
    """Verify that uploads exceeding SCANFORGE_MAX_UPLOAD_MB return HTTP 413 and delete partial files."""
    # Temporarily set max upload cap to 1 MB for testing
    monkeypatch.setattr(settings, "SCANFORGE_MAX_UPLOAD_MB", 1)

    # Generate 1.5 MB test payload
    oversized_bytes = b"0" * int(1.5 * 1024 * 1024)
    files = {"file": ("large_video.mp4", io.BytesIO(oversized_bytes), "video/mp4")}
    data = {"scan_type": "photo", "quality": "draft"}

    response = client.post("/api/jobs", files=files, data=data)
    assert response.status_code == 413
    assert "exceeds maximum allowed upload size" in response.json()["detail"]

    # Verify no file remains in uploads
    # Check upload directory for any stray large_video.mp4
    upload_files = list(storage_service.uploads_dir.glob("**/large_video.mp4"))
    assert len(upload_files) == 0, f"Partial upload was not deleted from disk: {upload_files}"
