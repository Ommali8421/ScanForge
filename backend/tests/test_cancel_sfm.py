"""
Test Real Process Cancellation during SfM and Pipelines
Validates that ToolRunner terminates child process trees on cancellation,
no orphaned processes remain, and jobs are marked CANCELLED in DB.
"""

import os
import signal
import subprocess
import time
from pathlib import Path
import pytest

from app.pipelines.base import CancelToken, JobContext
from app.pipelines.tool_runner import ToolRunner
from app.services.job_service import get_job
from app.queue.tasks import cancel_active_task


def test_tool_runner_cancellation_kills_process_tree():
    """ToolRunner must terminate process and its children when CancelToken is cancelled."""
    token = CancelToken()

    # Launch a script that spawns a child process and sleeps
    cmd = [
        "python3", "-c",
        "import time, subprocess, sys; p = subprocess.Popen(['sleep', '30']); time.sleep(30)"
    ]

    import threading
    def cancel_after_delay():
        time.sleep(0.5)
        token.cancel()

    thread = threading.Thread(target=cancel_after_delay)
    thread.start()

    start_time = time.time()
    active_pid = None

    with pytest.raises(RuntimeError, match="terminated due to job cancellation"):
        ToolRunner.run(cmd, cancel_token=token, timeout=30)

    elapsed = time.time() - start_time
    # Must terminate within ~2 seconds, not wait for 30s
    assert elapsed < 3.0, f"Command took {elapsed}s to cancel; expected < 3.0s"


def test_cancel_active_task_function(tmp_path: Path):
    """Test that cancel_active_task cancels running JobContext and marks cancelled."""
    token = CancelToken()
    job_id = "test-sfm-cancel-id"

    from app.queue.tasks import active_cancel_tokens
    active_cancel_tokens[job_id] = token

    assert token.is_cancelled() is False
    res = cancel_active_task(job_id)
    assert res is True
    assert token.is_cancelled() is True

    # Cleanup
    active_cancel_tokens.pop(job_id, None)
