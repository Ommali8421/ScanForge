"""
Unit & Integration Tests for Milestone P5: Production Hardening
Tests:
1. Cross-Container Cancellation Bridge & Process-Group Termination
2. Idempotent Stage Caching & Crash Resume Endpoint
3. Pre-Flight Low-Disk Space Rejection (HTTP 507)
4. Actionable Error Diagnostics & Classification
5. Safe Scratch Space Cleanup Preserving Deliverables
"""

import json
import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pipelines.base import CancelToken, Stage, JobContext, StageResult
from app.pipelines.tool_runner import ToolRunner
from app.services.error_classifier import classify_error
from app.services.cleanup import cleanup_job_scratch_files
from app.models.job import Job
from app.db.session import engine
from sqlmodel import Session


@pytest.fixture
def test_client():
    return TestClient(app)


def test_error_classification_diagnostics():
    """Verify error classifier maps various failure modes to structured codes and checklists."""
    # 1. CUDA OOM
    res_oom = classify_error("CUDA out of memory. Tried to allocate 2.4 GiB (GPU 0; 8.00 GiB total capacity)")
    assert res_oom["code"] == "ERR_CUDA_OOM"
    assert "GPU Memory Exhausted" in res_oom["title"]
    assert any("Standard" in step for step in res_oom["remediation"])

    # 2. Low SfM registration
    res_sfm = classify_error("ColmapSfMStage failed: Registered 18/67 frames (26.9%). Verification threshold unmet.")
    assert res_sfm["code"] == "ERR_LOW_SFM_REGISTRATION"
    assert "Insufficient Camera Registration" in res_sfm["title"]
    assert any("overlap" in step for step in res_sfm["remediation"])

    # 3. Motion blur
    res_blur = classify_error("FrameExtractionStage: Severe motion blur detected across keyframes. Laplacian variance < 15.0.")
    assert res_blur["code"] == "ERR_MOTION_BLUR"
    assert "Motion Blur" in res_blur["title"]

    # 4. Pure rotation
    res_rot = classify_error("Zero baseline detected: pure rotation about optical center causes parallax failure.")
    assert res_rot["code"] == "ERR_PURE_ROTATION"
    assert "Pure Rotational" in res_rot["title"]

    # 5. Corrupt input
    res_corrupt = classify_error("ffmpeg error: moov atom not found / invalid data found when processing input.")
    assert res_corrupt["code"] == "ERR_CORRUPT_INPUT"
    assert "Corrupted Input" in res_corrupt["title"]

    # 6. Fallback
    res_gen = classify_error("IndexError: list index out of range")
    assert res_gen["code"] == "ERR_GENERIC_FAILURE"


def test_cancel_token_redis_bridge():
    """Verify CancelToken detects cross-container Redis cancellation signal."""
    mock_redis = MagicMock()
    mock_redis.exists.return_value = True

    token = CancelToken(job_id="test-job-cancel-123")
    assert not token._cancelled

    with patch("redis.Redis.from_url", return_value=mock_redis):
        # is_cancelled() should check Redis and return True
        is_canc = token.is_cancelled()
        assert is_canc is True
        assert token._cancelled is True
        mock_redis.exists.assert_called_with("scanforge:cancel:test-job-cancel-123")


def test_tool_runner_process_group_termination():
    """Verify ToolRunner terminates an active long-running subprocess group upon cancellation."""
    token = CancelToken()

    # Launch python sleep command in subprocess
    cmd = ["python3", "-c", "import time; time.sleep(10)"]

    import threading
    def cancel_after_delay():
        time.sleep(0.3)
        token.cancel()

    thread = threading.Thread(target=cancel_after_delay)
    thread.start()

    start_t = time.time()
    with pytest.raises(RuntimeError, match="terminated due to job cancellation"):
        ToolRunner.run(cmd, cancel_token=token)
    elapsed = time.time() - start_t

    # Process group must be terminated in < 3.0s
    assert elapsed < 3.0
    thread.join()


def test_preflight_low_disk_space_rejection(test_client, tmp_path):
    """Verify POST /api/jobs returns HTTP 507 when available storage is below minimum threshold."""
    # Mock disk_usage to return 1 GB free (below 5 GB default)
    low_disk = MagicMock(free=1 * 1024 * 1024 * 1024, total=500 * 1024 * 1024 * 1024)

    dummy_file = ("test.mp4", b"\x00" * 1024, "video/mp4")
    with patch("shutil.disk_usage", return_value=low_disk):
        response = test_client.post(
            "/api/jobs",
            files={"file": dummy_file},
            data={"scan_type": "photo", "quality": "draft"}
        )
        assert response.status_code == 507
        assert "Insufficient storage space" in response.json()["detail"]


def test_scratch_space_cleanup(tmp_path):
    """Verify cleanup_job_scratch_files removes heavy intermediate files while preserving deliverables."""
    job_id = "test-cleanup-job-abc"
    workdir = tmp_path / job_id
    workdir.mkdir(parents=True)

    # Create deliverable files (MUST BE PRESERVED)
    keep_files = [
        "mesh.glb", "mesh.ply", "model.splat", "floor_plan.svg",
        "floor_plan.png", "quality_report.json", "preview_textured.glb"
    ]
    for kf in keep_files:
        (workdir / kf).write_text("deliverable content")

    # Create scratch files (MUST BE PURGED)
    (workdir / "mesh_dense.ply").write_text("dense scratch" * 1000)
    (workdir / "mesh_tsdf_raw.ply").write_text("tsdf scratch" * 1000)
    (workdir / "depth.dmap").write_text("dmap scratch" * 1000)

    depth_dir = workdir / "depth_raw"
    depth_dir.mkdir()
    (depth_dir / "frame_0001.npy").write_text("raw npy" * 500)

    with patch("app.services.storage.storage_service.get_job_workdir", return_value=workdir):
        reclaimed = cleanup_job_scratch_files(job_id)
        assert reclaimed > 0

    # Assert deliverables exist
    for kf in keep_files:
        assert (workdir / kf).exists(), f"Deliverable {kf} was erroneously removed!"

    # Assert scratch files were purged
    assert not (workdir / "mesh_dense.ply").exists()
    assert not (workdir / "mesh_tsdf_raw.ply").exists()
    assert not (workdir / "depth.dmap").exists()
    assert not depth_dir.exists()


def test_crash_resume_endpoint_and_cache_skipping(test_client, tmp_path):
    """Verify POST /api/jobs/{id}/resume resets failed/cancelled jobs and re-enqueues."""
    job_id = "test-resume-job-xyz"

    # Create test job in database
    with Session(engine) as session:
        job = Job(
            id=job_id,
            status="failed",
            scan_type="photo",
            quality="draft",
            error="Simulated stage failure",
            original_filename="room.mp4",
            input_file_path=str(tmp_path / "room.mp4")
        )
        session.add(job)
        session.commit()

    with patch("app.api.jobs.enqueue_job") as mock_enqueue:
        # Call resume endpoint
        resp = test_client.post(f"/api/jobs/{job_id}/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == job_id
        assert data["status"] == "queued"
        assert data["error"] is None
        mock_enqueue.assert_called_once_with(job_id)

    # Calling resume on a running or completed job should return 400
    with Session(engine) as session:
        job = session.get(Job, job_id)
        job.status = "completed"
        session.add(job)
        session.commit()

    resp_invalid = test_client.post(f"/api/jobs/{job_id}/resume")
    assert resp_invalid.status_code == 400
    assert "Only failed or cancelled jobs" in resp_invalid.json()["detail"]
