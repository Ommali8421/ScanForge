"""
Tier 3: Cross-Feature Combinations E2E Tests
Exercises pairwise and multi-feature interactions:
1. Scan Type x Quality Presets x Output Formats
2. 3DGS Gaussian Splatting x Web Splat Packaging (.ply, .splat)
3. Consecutive Non-Compounding Scale Calibrations with Factor Compounding
4. Concurrent Pipeline Execution with SSE Event Streaming
5. Job Cancellation Lifecycle and SSE Termination Events
6. Up-Axis and Spatial Coordinate Mapping in Quality Reports
"""

import io
import json
import struct
import threading
import time
import pytest
from fastapi.testclient import TestClient

from app.services.job_service import get_job
from .conftest import submit_job, complete_job_pipeline, make_dummy_mp4


# ============================================================================
# 1. Scan Type x Quality Presets x Output Formats Matrix
# ============================================================================

@pytest.mark.parametrize("preset,formats", [
    ("draft", ["glb"]),
    ("standard", ["glb", "obj"]),
    ("high", ["glb", "obj", "ply"]),
])
def test_photo_scan_matrix_presets_and_formats(client: TestClient, preset: str, formats: list[str]):
    """1. Verify Photo scan across presets and format permutations."""
    job_id = submit_job(
        client,
        scan_type="photo",
        quality=preset,
        output_formats=formats,
        filename=f"tour_{preset}.mp4"
    )
    complete_job_pipeline(job_id)

    # Verify status
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    job = res.json()
    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert job["quality"] == preset

    # Verify artifacts
    art_res = client.get(f"/api/jobs/{job_id}/artifacts")
    assert art_res.status_code == 200
    artifacts = art_res.json()
    available_fmts = {a["format"] for a in artifacts}

    for fmt in formats:
        assert fmt in available_fmts, f"Format {fmt} missing from artifacts for preset {preset}"
        down_res = client.get(f"/api/jobs/{job_id}/download/{fmt}")
        assert down_res.status_code == 200, f"Download failed for format {fmt}"
        assert len(down_res.content) > 0


# ============================================================================
# 2. 3DGS Gaussian Splatting x Web Splat Packaging
# ============================================================================

def test_gaussian_splat_scan_deliverable_formats(client: TestClient):
    """2. Verify 3DGS scan generates valid .ply and 32-byte compact .splat web deliverables."""
    job_id = submit_job(
        client,
        scan_type="gaussian_splat",
        quality="standard",
        output_formats=["ply", "splat"],
        filename="splat_room.mp4"
    )
    complete_job_pipeline(job_id)

    # Verify artifacts list
    art_res = client.get(f"/api/jobs/{job_id}/artifacts")
    assert art_res.status_code == 200
    artifacts = art_res.json()
    artifact_fmts = {a["format"] for a in artifacts}
    assert "ply" in artifact_fmts
    assert "splat" in artifact_fmts

    # Download .splat: must be multiple of 32 bytes
    splat_res = client.get(f"/api/jobs/{job_id}/download/splat")
    assert splat_res.status_code == 200
    splat_bytes = splat_res.content
    assert len(splat_bytes) > 0
    assert len(splat_bytes) % 32 == 0, f"Binary splat size {len(splat_bytes)} is not a multiple of 32 bytes"

    # Download .ply: must have valid PLY header with Gaussian attributes
    ply_res = client.get(f"/api/jobs/{job_id}/download/ply")
    assert ply_res.status_code == 200
    ply_text = ply_res.text
    assert ply_text.startswith("ply")
    assert "element vertex" in ply_text
    assert "opacity" in ply_text
    assert "scale_" in ply_text


# ============================================================================
# 3. Consecutive Non-Compounding Scale Calibrations
# ============================================================================

def test_consecutive_scale_calibrations_factor_compounding(client: TestClient):
    """3. Verify multi-step consecutive calibrations compound factors accurately without drift."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    # Initial check
    initial_job = client.get(f"/api/jobs/{job_id}").json()
    assert initial_job["cumulative_scale"] == 1.0

    # Step 1: Measured 2.0 -> Real 3.0 (Factor 1.5, Cumulative 1.5)
    c1 = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [2.0, 0.0, 0.0],
        "real_distance": 3.0
    }).json()
    assert c1["applied_factor"] == 1.5
    assert c1["cumulative_scale"] == 1.5

    # Step 2: Measured 1.5 -> Real 3.0 (Factor 2.0, Cumulative 1.5 * 2.0 = 3.0)
    c2 = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.5, 0.0, 0.0],
        "real_distance": 3.0
    }).json()
    assert c2["applied_factor"] == 2.0
    assert c2["cumulative_scale"] == 3.0

    # Step 3: Measured 3.0 -> Real 1.5 (Factor 0.5, Cumulative 3.0 * 0.5 = 1.5)
    c3 = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [3.0, 0.0, 0.0],
        "real_distance": 1.5
    }).json()
    assert c3["applied_factor"] == 0.5
    assert c3["cumulative_scale"] == 1.5

    # Quality report check
    rep = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep["cumulative_scale"] == 1.5
    assert rep["is_calibrated"] is True


# ============================================================================
# 4. Concurrent Pipeline Execution with SSE Event Streaming
# ============================================================================

def test_concurrent_execution_and_sse_streaming(client: TestClient):
    """4. Connect to SSE stream before pipeline execution, stream live progression, and verify completion."""
    job_id = submit_job(client)

    events_received = []
    stop_event = threading.Event()

    def sse_listener():
        with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
            for line in response.iter_lines():
                if stop_event.is_set():
                    break
                if line:
                    events_received.append(line)
                    if "event: completed" in line:
                        break

    thread = threading.Thread(target=sse_listener, daemon=True)
    thread.start()

    # Allow listener to connect
    time.sleep(0.3)

    # Run the pipeline
    complete_job_pipeline(job_id)

    # Wait for listener to catch completion
    thread.join(timeout=5.0)
    stop_event.set()

    full_stream = "\n".join(events_received)
    assert "event: stage" in full_stream
    assert "event: completed" in full_stream


# ============================================================================
# 5. Job Cancellation Lifecycle and SSE Termination Events
# ============================================================================

def test_active_job_cancellation_lifecycle(client: TestClient):
    """5. Verify job cancellation sets status to cancelled and emits terminal event."""
    job_id = submit_job(client)

    # Cancel the job
    cancel_res = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # Verify query returns cancelled status
    job_data = client.get(f"/api/jobs/{job_id}").json()
    assert job_data["status"] == "cancelled"

    # Connect to SSE: should emit event: cancelled immediately
    with client.stream("GET", f"/api/jobs/{job_id}/events") as sse_res:
        content = ""
        for chunk in sse_res.iter_text():
            content += chunk
        assert "event: cancelled" in content


# ============================================================================
# 6. Up-Axis and Spatial Coordinate Mapping in Quality Reports
# ============================================================================

def test_up_axis_and_unit_combinations_on_report(client: TestClient):
    """6. Verify up_axis='z' vs 'y' spatial dimension mappings in quality report."""
    job_id_y = submit_job(client, options={"up_axis": "y", "units": "m"})
    complete_job_pipeline(job_id_y)
    rep_y = client.get(f"/api/jobs/{job_id_y}/report").json()
    assert rep_y["up_axis"] == "y"
    assert rep_y["dimensions_meters"]["length"] > 0
    assert rep_y["dimensions_meters"]["height"] > 0
    assert rep_y["dimensions_meters"]["width"] > 0

    job_id_z = submit_job(client, options={"up_axis": "z", "units": "m"})
    complete_job_pipeline(job_id_z)
    rep_z = client.get(f"/api/jobs/{job_id_z}/report").json()
    assert rep_z["up_axis"] == "z"
    assert rep_z["dimensions_meters"]["length"] > 0
    assert rep_z["dimensions_meters"]["width"] > 0
    assert rep_z["dimensions_meters"]["height"] > 0
