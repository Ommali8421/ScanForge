"""
Tier 4: Real-World Scenarios E2E Tests
Exercises complete, multi-step end-to-end user journeys:
1. Scenario 1: Complete Photo Walkthrough to Deliverables Journey
2. Scenario 2: Interactive Studio 3D Measure & Scale Calibration Flow
3. Scenario 3: 3DGS Gaussian Splatting Scan and Packaging Journey
4. Scenario 4: Resilient Error Recovery, Download-All, and Purge Lifecycle
5. Scenario 5: Multi-Job Concurrency and Workspace Isolation Flow
"""

import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.services.storage import storage_service
from .conftest import submit_job, complete_job_pipeline, make_dummy_mp4


# ============================================================================
# Scenario 1: Complete Photo Walkthrough to Deliverables Journey
# ============================================================================

def test_user_journey_full_photo_walkthrough_to_deliverables(client: TestClient):
    """
    Scenario 1: Full user journey from video upload to textured deliverables.
    - User inspects system capabilities.
    - User uploads indoor walkthrough video.
    - System enqueues job and streams SSE progress.
    - Job executes to completion.
    - User downloads GLB and OBJ ZIP deliverables.
    - User checks initial quality report.
    """
    # Step 1: Check capabilities
    caps_res = client.get("/api/capabilities")
    assert caps_res.status_code == 200
    caps = caps_res.json()
    assert "photo" in caps["scan_types"]

    # Step 2: Upload photo scan job
    job_id = submit_job(
        client,
        scan_type="photo",
        quality="standard",
        output_formats=["glb", "obj"],
        options={"mesh_route": "auto", "up_axis": "y"},
        filename="apartment_walkthrough.mp4"
    )
    assert job_id is not None

    # Step 3: Stream initial SSE connection
    with client.stream("GET", f"/api/jobs/{job_id}/events") as sse_stream:
        # Replay event must arrive immediately
        assert sse_stream.status_code == 200

    # Step 4: Pipeline executes in background
    complete_job_pipeline(job_id)

    # Step 5: Verify completed status
    job_res = client.get(f"/api/jobs/{job_id}")
    assert job_res.status_code == 200
    job = job_res.json()
    assert job["status"] == "completed"
    assert job["progress"] == 100

    # Step 6: Query artifacts and download
    art_res = client.get(f"/api/jobs/{job_id}/artifacts")
    assert art_res.status_code == 200
    artifacts = art_res.json()
    assert len(artifacts) >= 2

    glb_res = client.get(f"/api/jobs/{job_id}/download/glb")
    assert glb_res.status_code == 200
    assert len(glb_res.content) > 0

    obj_res = client.get(f"/api/jobs/{job_id}/download/obj")
    assert obj_res.status_code == 200
    assert len(obj_res.content) > 0

    # Step 7: Inspect quality report
    rep_res = client.get(f"/api/jobs/{job_id}/report")
    assert rep_res.status_code == 200
    rep = rep_res.json()
    assert rep["is_calibrated"] is False
    assert rep["cumulative_scale"] == 1.0
    assert rep["dimensions_meters"]["length"] > 0
    assert rep["dimensions_meters"]["height"] > 0
    assert rep["dimensions_meters"]["width"] > 0


# ============================================================================
# Scenario 2: Interactive Studio 3D Measure & Scale Calibration Flow
# ============================================================================

def test_user_journey_studio_scale_calibration_and_remodeling(client: TestClient):
    """
    Scenario 2: User measures two points in 3D studio viewer and calibrates metric scale.
    - Initial uncalibrated inspection.
    - Two-point measurement [0,0,0] to [0,2,0] (measured 2.0m).
    - User calibrates with real distance 2.5m (factor 1.25x).
    - Report dimensions updated instantaneously.
    - Second fine-tuning calibration (measured 2.5m -> real 3.0m, factor 1.2x).
    - Cumulative scale multiplies to 1.5x (1.25 * 1.2 = 1.50).
    - Download recalibrated GLB deliverable.
    """
    job_id = submit_job(client, scan_type="photo", quality="standard")
    complete_job_pipeline(job_id)

    # Initial report
    rep0 = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep0["is_calibrated"] is False
    len0 = rep0["dimensions_meters"]["length"]

    # Step 1: First calibration (2.0m measured -> 2.5m real => factor 1.25)
    cal1_res = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [0.0, 2.0, 0.0],
        "real_distance": 2.5
    })
    assert cal1_res.status_code == 202
    data1 = cal1_res.json()
    assert data1["measured_distance"] == 2.0
    assert data1["applied_factor"] == 1.25
    assert data1["cumulative_scale"] == 1.25

    # Verify report is immediately updated
    rep1 = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep1["is_calibrated"] is True
    assert rep1["cumulative_scale"] == 1.25
    assert rep1["dimensions_meters"]["length"] == pytest.approx(len0 * 1.25, abs=0.2)

    # Step 2: Second calibration (measured 2.5m -> real 3.0m => factor 1.2)
    cal2_res = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [0.0, 2.5, 0.0],
        "real_distance": 3.0
    })
    assert cal2_res.status_code == 202
    data2 = cal2_res.json()
    assert data2["applied_factor"] == 1.2
    assert data2["cumulative_scale"] == 1.5

    # Verify cumulative compounding on report
    rep2 = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep2["cumulative_scale"] == 1.5
    assert rep2["dimensions_meters"]["length"] == pytest.approx(len0 * 1.5, abs=0.2)

    # Verify recalibrated GLB download succeeds
    glb_res = client.get(f"/api/jobs/{job_id}/download/glb")
    assert glb_res.status_code == 200
    assert len(glb_res.content) > 0


# ============================================================================
# Scenario 3: 3DGS Gaussian Splatting Scan and Packaging Journey
# ============================================================================

def test_user_journey_3dgs_splatting_flow(client: TestClient):
    """
    Scenario 3: 3DGS reconstruction pipeline and splat deliverable packaging.
    - Submit 3DGS capture with PLY and SPLAT outputs.
    - Pipeline executes splat generation.
    - Artifacts include both PLY and compact 32-byte .splat.
    - User calibrates scale on the splat model.
    - Download calibrated .splat and verify valid binary packing.
    """
    job_id = submit_job(
        client,
        scan_type="gaussian_splat",
        quality="standard",
        output_formats=["ply", "splat"],
        filename="heritage_room_splat.mp4"
    )
    complete_job_pipeline(job_id)

    # Verify artifacts
    art_res = client.get(f"/api/jobs/{job_id}/artifacts")
    assert art_res.status_code == 200
    artifacts = art_res.json()
    art_names = [a["filename"] for a in artifacts]
    assert any(name.endswith(".splat") for name in art_names)
    assert any(name.endswith(".ply") for name in art_names)

    # Scale calibrate splat job
    cal_res = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.0, 0.0, 0.0],
        "real_distance": 1.5
    })
    assert cal_res.status_code == 202
    assert cal_res.json()["cumulative_scale"] == 1.5

    # Download splat deliverable
    splat_res = client.get(f"/api/jobs/{job_id}/download/splat")
    assert splat_res.status_code == 200
    content = splat_res.content
    assert len(content) > 0
    assert len(content) % 32 == 0


# ============================================================================
# Scenario 4: Resilient Error Recovery, Download-All, and Purge Lifecycle
# ============================================================================

def test_user_journey_error_recovery_and_purging_lifecycle(client: TestClient):
    """
    Scenario 4: Complete lifecycle test including error recovery, batch download, and disk purge.
    - Submit and complete scan.
    - Attempt invalid operations (request missing format -> 404).
    - Download entire deliverables bundle via /download-all ZIP.
    - Delete job via DELETE /api/jobs/{id}.
    - Confirm all storage and records are purged.
    """
    job_id = submit_job(client, output_formats=["glb", "obj"])
    complete_job_pipeline(job_id)

    # Attempt invalid format download
    bad_down = client.get(f"/api/jobs/{job_id}/download/nonexistent_format")
    assert bad_down.status_code == 404

    # Download all artifacts ZIP bundle
    all_res = client.get(f"/api/jobs/{job_id}/download-all")
    assert all_res.status_code == 200
    assert all_res.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(all_res.content), "r") as zf:
        assert len(zf.namelist()) >= 2

    # Verify workdir exists before delete
    workdir = storage_service.get_job_workdir(job_id)
    assert workdir.exists()

    # Delete job
    del_res = client.delete(f"/api/jobs/{job_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Confirm storage cleanup
    assert not workdir.exists()

    # Confirm subsequent queries return 404
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/download/glb").status_code == 404


# ============================================================================
# Scenario 5: Multi-Job Concurrency and Workspace Isolation Flow
# ============================================================================

def test_user_journey_multi_scan_concurrency_and_workspace_isolation(client: TestClient):
    """
    Scenario 5: Multi-job concurrency and workspace isolation.
    - Submit Job A (Photo scan) and Job B (Gaussian Splat scan).
    - Execute both pipelines.
    - Confirm Job A has photo mesh artifacts (GLB/OBJ).
    - Confirm Job B has splat artifacts (SPLAT/PLY).
    - Confirm independent logs, reports, and downloads.
    """
    # Submit Job A
    job_a = submit_job(client, scan_type="photo", output_formats=["glb", "obj"], filename="job_a.mp4")
    # Submit Job B
    job_b = submit_job(client, scan_type="gaussian_splat", output_formats=["ply", "splat"], filename="job_b.mp4")

    # Complete both
    complete_job_pipeline(job_a)
    complete_job_pipeline(job_b)

    # Inspect Job A
    a_data = client.get(f"/api/jobs/{job_a}").json()
    assert a_data["status"] == "completed"
    assert a_data["scan_type"] == "photo"
    a_art = client.get(f"/api/jobs/{job_a}/artifacts").json()
    a_fmts = {item["format"] for item in a_art}
    assert "glb" in a_fmts

    # Inspect Job B
    b_data = client.get(f"/api/jobs/{job_b}").json()
    assert b_data["status"] == "completed"
    assert b_data["scan_type"] == "gaussian_splat"
    b_art = client.get(f"/api/jobs/{job_b}/artifacts").json()
    b_fmts = {item["format"] for item in b_art}
    assert "splat" in b_fmts

    # Verify download-all for each job produces distinct archives
    all_a = client.get(f"/api/jobs/{job_a}/download-all")
    all_b = client.get(f"/api/jobs/{job_b}/download-all")
    assert all_a.status_code == 200
    assert all_b.status_code == 200
    assert all_a.content != all_b.content
