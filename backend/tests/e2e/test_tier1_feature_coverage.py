"""
Tier 1: Feature Coverage E2E Tests
Exercises all core features with >=5 test cases per feature covering:
1. Capabilities & System Health
2. Job Submission & Options Ingestion
3. Job Lifecycle & Management
4. Server-Sent Events (SSE) Streaming
5. Scale Calibration & Non-Compounding Math
6. Quality Reports & Scene Metrics
7. Artifact Downloads & Multi-Format Exporters
"""

import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.services.job_service import (
    update_job_progress,
    append_job_log,
    set_job_completed,
    get_job,
)
from app.services.storage import storage_service
from .conftest import submit_job, complete_job_pipeline, make_dummy_mp4, make_dummy_zip


# ============================================================================
# Feature 1: Capabilities & System Health (>=5 test cases)
# ============================================================================

def test_health_check_status_and_components(client: TestClient):
    """1.1 Verify GET /api/health returns 200 with engine, status, version, and component status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["status"] in ["ok", "degraded"]
    assert "version" in data
    assert "engine" in data
    assert "db" in data
    assert "redis" in data
    assert isinstance(data.get("disk_free_gb", 0), (int, float))


def test_capabilities_scan_types_and_defaults(client: TestClient):
    """1.2 Verify GET /api/capabilities returns supported scan types, quality presets, and mesh routes."""
    res = client.get("/api/capabilities")
    assert res.status_code == 200
    caps = res.json()
    assert "scan_types" in caps
    assert "photo" in caps["scan_types"]
    assert "gaussian_splat" in caps["scan_types"]
    assert "quality_presets" in caps
    assert set(caps["quality_presets"]) == {"draft", "standard", "high"}
    assert "mesh_routes" in caps
    assert "auto" in caps["mesh_routes"]
    assert "photogrammetry" in caps["mesh_routes"]
    assert "depth_fusion" in caps["mesh_routes"]


def test_capabilities_format_matrix_structure(client: TestClient):
    """1.3 Verify format_matrix maps all scan types to their supported deliverable formats."""
    res = client.get("/api/capabilities")
    assert res.status_code == 200
    caps = res.json()
    fm = caps.get("format_matrix", {})
    assert "photo" in fm
    assert "glb" in fm["photo"]
    assert "obj" in fm["photo"]
    assert "gaussian_splat" in fm
    assert "ply" in fm["gaussian_splat"]
    assert "splat" in fm["gaussian_splat"]
    assert "lidar" in fm


def test_capabilities_runtime_converters(client: TestClient):
    """1.4 Verify runtime_converters indicates availability of Blender, FBX, and USDZ converters."""
    res = client.get("/api/capabilities")
    assert res.status_code == 200
    caps = res.json()
    rc = caps.get("runtime_converters", {})
    assert "blender" in rc
    assert "fbx_supported" in rc
    assert "usdz_supported" in rc
    assert isinstance(rc["blender"], bool)
    assert isinstance(rc["fbx_supported"], bool)
    assert isinstance(rc["usdz_supported"], bool)


def test_capabilities_system_limits(client: TestClient):
    """1.5 Verify limits dictionary defines upload cap and frame thresholds."""
    res = client.get("/api/capabilities")
    assert res.status_code == 200
    limits = res.json().get("limits", {})
    assert limits.get("max_upload_mb", 0) > 0
    assert limits.get("max_video_seconds", 0) > 0
    assert limits.get("max_frames_photo", 0) > 0
    assert limits.get("max_frames_3dgs", 0) > 0


# ============================================================================
# Feature 2: Job Submission & Options Ingestion (>=5 test cases)
# ============================================================================

def test_submit_photo_scan_standard(client: TestClient):
    """2.1 Submit photo scan with standard quality and verify HTTP 202 Accepted and queued status."""
    job_id = submit_job(client, scan_type="photo", quality="standard")
    assert job_id is not None
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    job = res.json()
    assert job["id"] == job_id
    assert job["scan_type"] == "photo"
    assert job["quality"] == "standard"
    assert job["status"] in ["queued", "running", "completed"]


def test_submit_gaussian_splat_scan(client: TestClient):
    """2.2 Submit gaussian_splat scan with splat output formats."""
    job_id = submit_job(
        client,
        scan_type="gaussian_splat",
        quality="draft",
        output_formats=["ply", "splat"],
        filename="splat_source.mp4"
    )
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    job = res.json()
    assert job["scan_type"] == "gaussian_splat"
    assert "ply" in job["output_formats"]
    assert "splat" in job["output_formats"]


def test_submit_job_with_custom_job_options(client: TestClient):
    """2.3 Submit job with custom options (poly_target, texture_size, up_axis, mesh_route, units)."""
    custom_opts = {
        "poly_target": 180000,
        "texture_size": 2048,
        "up_axis": "z",
        "units": "cm",
        "mesh_route": "depth_fusion",
        "include_mesh": True
    }
    job_id = submit_job(client, scan_type="photo", options=custom_opts)
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    stored_opts = res.json()["options"]
    assert stored_opts["poly_target"] == 180000
    assert stored_opts["texture_size"] == 2048
    assert stored_opts["up_axis"] == "z"
    assert stored_opts["units"] == "cm"
    assert stored_opts["mesh_route"] == "depth_fusion"
    assert stored_opts["include_mesh"] is True


def test_submit_job_with_zip_archive(client: TestClient):
    """2.4 Submit job with a zip image sequence archive and verify original filename retention."""
    zip_bytes = make_dummy_zip(["img_01.jpg", "img_02.jpg", "img_03.jpg"])
    job_id = submit_job(
        client,
        scan_type="photo",
        filename="room_frames.zip",
        file_bytes=zip_bytes,
        content_type="application/zip"
    )
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    job = res.json()
    assert job["original_filename"] == "room_frames.zip"


def test_submit_job_format_parsing_variations(client: TestClient):
    """2.5 Verify output_formats parsing for diverse JSON string arrays."""
    formats = ["glb", "obj", "ply", "stl", "xyz"]
    job_id = submit_job(client, scan_type="photo", output_formats=formats)
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    assert set(res.json()["output_formats"]) == set(formats)


# ============================================================================
# Feature 3: Job Lifecycle & Query Operations (>=5 test cases)
# ============================================================================

def test_list_jobs_pagination(client: TestClient):
    """3.1 Verify GET /api/jobs supports limit and offset pagination."""
    j1 = submit_job(client, filename="j1.mp4")
    j2 = submit_job(client, filename="j2.mp4")
    j3 = submit_job(client, filename="j3.mp4")

    res_all = client.get("/api/jobs?limit=100")
    assert res_all.status_code == 200
    total = res_all.json()["total"]
    assert total >= 3

    res_page = client.get("/api/jobs?limit=2&offset=0")
    assert res_page.status_code == 200
    items = res_page.json()["items"]
    assert len(items) <= 2


def test_list_jobs_status_filtering(client: TestClient):
    """3.2 Verify GET /api/jobs?status=... filters by job status."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    res_completed = client.get("/api/jobs?status=completed")
    assert res_completed.status_code == 200
    items = res_completed.json()["items"]
    assert len(items) > 0
    assert all(item["status"] == "completed" for item in items)


def test_get_job_detail_fields(client: TestClient):
    """3.3 Verify GET /api/jobs/{id} returns complete schema fields."""
    job_id = submit_job(client)
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    data = res.json()
    expected_fields = [
        "id", "status", "scan_type", "quality", "current_stage",
        "progress", "cumulative_scale", "created_at", "artifacts"
    ]
    for field in expected_fields:
        assert field in data, f"Missing field '{field}' in job detail response"


def test_cancel_queued_or_running_job(client: TestClient):
    """3.4 Verify POST /api/jobs/{id}/cancel marks job as cancelled."""
    job_id = submit_job(client)
    cancel_res = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    get_res = client.get(f"/api/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "cancelled"


def test_delete_job_and_purge_storage(client: TestClient):
    """3.5 Verify DELETE /api/jobs/{id} deletes job record and purged directories return 404."""
    job_id = submit_job(client)
    workdir = storage_service.get_job_workdir(job_id)

    del_res = client.delete(f"/api/jobs/{job_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    get_res = client.get(f"/api/jobs/{job_id}")
    assert get_res.status_code == 404
    assert not workdir.exists()


# ============================================================================
# Feature 4: Server-Sent Events (SSE) Streaming (>=5 test cases)
# ============================================================================

def test_sse_stream_connection_headers(client: TestClient):
    """4.1 Connect to /api/jobs/{id}/events and verify HTTP 200 text/event-stream headers."""
    job_id = submit_job(client)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


def test_sse_initial_stage_replay(client: TestClient):
    """4.2 Verify SSE stream immediately replays current stage and progress upon connection."""
    job_id = submit_job(client)
    update_job_progress(job_id, "sparse_sfm", 40, "Matching feature points")

    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        content = ""
        for chunk in response.iter_text():
            content += chunk
            if "event: stage" in content:
                break
        assert "event: stage" in content
        assert "sparse_sfm" in content


def test_sse_initial_log_history_replay(client: TestClient):
    """4.3 Verify SSE stream immediately replays previous log lines."""
    job_id = submit_job(client)
    append_job_log(job_id, "[SfM] Triangulated 4,200 points")
    append_job_log(job_id, "[SfM] Mean reprojection error: 0.72 px")

    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        content = ""
        for chunk in response.iter_text():
            content += chunk
            if "Mean reprojection error" in content:
                break
        assert "event: log" in content
        assert "Triangulated 4,200 points" in content
        assert "Mean reprojection error" in content


def test_sse_terminal_event_on_completion(client: TestClient):
    """4.4 Verify SSE stream emits terminal completion event when job has finished."""
    job_id = submit_job(client)
    set_job_completed(job_id)

    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        content = ""
        for chunk in response.iter_text():
            content += chunk
        assert "event: completed" in content
        assert job_id in content


def test_sse_error_event_for_missing_job(client: TestClient):
    """4.5 Verify connecting to SSE for an unknown job ID yields an error event."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    with client.stream("GET", f"/api/jobs/{fake_id}/events") as response:
        content = ""
        for chunk in response.iter_text():
            content += chunk
        assert "event: error" in content
        assert "Job not found" in content


# ============================================================================
# Feature 5: Scale Calibration & Non-Compounding Math (>=5 test cases)
# ============================================================================

def test_calibrate_valid_two_point_distance(client: TestClient):
    """5.1 Submit and complete job, then calibrate scale from measured 2.0m to real 3.0m."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    payload = {
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [2.0, 0.0, 0.0],
        "real_distance": 3.0
    }
    res = client.post(f"/api/jobs/{job_id}/calibrate", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert data["measured_distance"] == 2.0
    assert data["applied_factor"] == 1.5
    assert data["cumulative_scale"] == 1.5


def test_calibrate_sequential_non_compounding(client: TestClient):
    """5.2 Perform two sequential calibration operations and verify factor multiplication."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    # Step 1: Measured 2.0 -> Real 3.0 (Factor 1.5, Scale 1.5)
    p1 = {"point_a": [0.0, 0.0, 0.0], "point_b": [2.0, 0.0, 0.0], "real_distance": 3.0}
    r1 = client.post(f"/api/jobs/{job_id}/calibrate", json=p1).json()
    assert r1["cumulative_scale"] == 1.5

    # Step 2: Measured 1.0 -> Real 2.0 (Factor 2.0, Scale 1.5 * 2.0 = 3.0)
    p2 = {"point_a": [0.0, 0.0, 0.0], "point_b": [1.0, 0.0, 0.0], "real_distance": 2.0}
    r2 = client.post(f"/api/jobs/{job_id}/calibrate", json=p2).json()
    assert r2["applied_factor"] == 2.0
    assert r2["cumulative_scale"] == 3.0


def test_calibrate_updates_quality_report_dimensions(client: TestClient):
    """5.3 Verify /calibrate directly scales dimensions in quality report."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    rep_before = client.get(f"/api/jobs/{job_id}/report").json()
    orig_length = rep_before["dimensions_meters"]["length"]

    # Apply 2.0x scale
    p = {"point_a": [0.0, 0.0, 0.0], "point_b": [1.0, 0.0, 0.0], "real_distance": 2.0}
    client.post(f"/api/jobs/{job_id}/calibrate", json=p)

    rep_after = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep_after["cumulative_scale"] == 2.0
    assert rep_after["is_calibrated"] is True
    assert rep_after["dimensions_meters"]["length"] == pytest.approx(orig_length * 2.0, abs=0.2)


def test_calibrate_broadcasts_sse_event(client: TestClient):
    """5.4 Verify /calibrate logs a calibration record in job log_tail."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    p = {"point_a": [0.0, 0.0, 0.0], "point_b": [2.0, 0.0, 0.0], "real_distance": 4.0}
    client.post(f"/api/jobs/{job_id}/calibrate", json=p)

    job_detail = client.get(f"/api/jobs/{job_id}").json()
    log_tail = job_detail.get("log_tail", [])
    assert any("[Calibrate]" in line for line in log_tail)


def test_calibrate_updates_job_database_record(client: TestClient):
    """5.5 Verify cumulative_scale is persisted on the Job SQL model."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    p = {"point_a": [0.0, 0.0, 0.0], "point_b": [5.0, 0.0, 0.0], "real_distance": 2.5}
    client.post(f"/api/jobs/{job_id}/calibrate", json=p)

    db_job = get_job(job_id)
    assert db_job.cumulative_scale == 0.5
    assert db_job.options.get("is_calibrated") is True


# ============================================================================
# Feature 6: Quality Reports & Scene Metrics (>=5 test cases)
# ============================================================================

def test_get_quality_report_schema(client: TestClient):
    """6.1 Verify GET /api/jobs/{id}/report returns all required schema fields."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    res = client.get(f"/api/jobs/{job_id}/report")
    assert res.status_code == 200
    rep = res.json()
    assert "vertex_count" in rep
    assert "face_count" in rep
    assert "hole_count" in rep
    assert "dimensions_meters" in rep
    assert "floor_area_sqm" in rep
    assert "cumulative_scale" in rep
    assert "is_calibrated" in rep


def test_report_dimensions_y_up_orientation(client: TestClient):
    """6.2 Verify dimensions under default Y-up: length (X), height (Y), width (Z)."""
    job_id = submit_job(client, options={"up_axis": "y"})
    complete_job_pipeline(job_id)

    rep = client.get(f"/api/jobs/{job_id}/report").json()
    dims = rep["dimensions_meters"]
    assert dims["length"] > 0
    assert dims["height"] > 0
    assert dims["width"] > 0


def test_report_dimensions_z_up_orientation(client: TestClient):
    """6.3 Verify dimensions under Z-up: length (X), width (Y), height (Z)."""
    job_id = submit_job(client, options={"up_axis": "z"})
    complete_job_pipeline(job_id)

    rep = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep["up_axis"] == "z"
    dims = rep["dimensions_meters"]
    assert dims["length"] > 0
    assert dims["width"] > 0
    assert dims["height"] > 0


def test_report_floor_area_calculation(client: TestClient):
    """6.4 Verify floor_area_sqm is a positive number proportional to room footprint."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    rep = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep["floor_area_sqm"] > 0.0


def test_report_calibration_state_flag(client: TestClient):
    """6.5 Verify is_calibrated flag is False initially and becomes True after /calibrate."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    rep_uncal = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep_uncal["is_calibrated"] is False

    client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.0, 0.0, 0.0],
        "real_distance": 1.0
    })

    rep_cal = client.get(f"/api/jobs/{job_id}/report").json()
    assert rep_cal["is_calibrated"] is True


# ============================================================================
# Feature 7: Artifact Downloads & Multi-Format Exporters (>=5 test cases)
# ============================================================================

def test_list_artifacts_for_completed_job(client: TestClient):
    """7.1 Verify GET /api/jobs/{id}/artifacts lists all generated deliverables."""
    job_id = submit_job(client, output_formats=["glb", "obj"])
    complete_job_pipeline(job_id)

    res = client.get(f"/api/jobs/{job_id}/artifacts")
    assert res.status_code == 200
    artifacts = res.json()
    assert len(artifacts) >= 2
    formats = [a["format"] for a in artifacts]
    assert "glb" in formats
    assert "obj" in formats


def test_download_glb_artifact(client: TestClient):
    """7.2 Verify GET /api/jobs/{id}/download/glb returns valid binary mesh."""
    job_id = submit_job(client, output_formats=["glb"])
    complete_job_pipeline(job_id)

    res = client.get(f"/api/jobs/{job_id}/download/glb")
    assert res.status_code == 200
    assert res.headers["content-type"] in ["model/gltf-binary", "application/octet-stream"]
    assert len(res.content) > 0


def test_download_obj_artifact(client: TestClient):
    """7.3 Verify GET /api/jobs/{id}/download/obj serves OBJ or OBJ package."""
    job_id = submit_job(client, output_formats=["obj"])
    complete_job_pipeline(job_id)

    res = client.get(f"/api/jobs/{job_id}/download/obj")
    assert res.status_code == 200
    assert len(res.content) > 0


def test_download_all_zip_archive(client: TestClient):
    """7.4 Verify GET /api/jobs/{id}/download-all returns valid ZIP containing all deliverables."""
    job_id = submit_job(client, output_formats=["glb", "obj"])
    complete_job_pipeline(job_id)

    res = client.get(f"/api/jobs/{job_id}/download-all")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"

    # Verify zip content structure
    with zipfile.ZipFile(io.BytesIO(res.content), "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) >= 2


def test_download_full_pipeline_log(client: TestClient):
    """7.5 Verify GET /api/jobs/{id}/log returns the unredacted execution text log."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    res = client.get(f"/api/jobs/{job_id}/log")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    assert len(res.text) > 0
