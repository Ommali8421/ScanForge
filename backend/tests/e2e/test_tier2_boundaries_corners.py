"""
Tier 2: Boundary & Corner Cases E2E Tests
Adversarially probes the system with degenerate inputs, zero-values, out-of-bounds parameters, and invalid sequences:
1. Scale Calibration Boundaries (degenerate points, epsilon distance, malformed coordinates)
2. Upload & Ingestion Boundaries (file size caps, missing files, malformed JSON, 0-byte uploads)
3. Pagination & Query Boundaries (limit/offset validation, missing job IDs)
4. Artifacts & Downloads Boundaries (missing formats, ungenerated archives, non-existent logs)
"""

import io
import json
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services.storage import storage_service
from .conftest import submit_job, complete_job_pipeline, make_dummy_mp4


# ============================================================================
# Category 1: Scale Calibration Boundaries & Degenerate Points (>=5 tests)
# ============================================================================

def test_calibrate_zero_distance_same_points(client: TestClient):
    """1.1 Calibrate with identical points (distance 0.0) returns HTTP 400."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    payload = {
        "point_a": [1.5, 2.0, -0.5],
        "point_b": [1.5, 2.0, -0.5],
        "real_distance": 2.0
    }
    res = client.post(f"/api/jobs/{job_id}/calibrate", json=payload)
    assert res.status_code == 400
    assert "too close together" in res.json()["detail"].lower()


def test_calibrate_epsilon_distance_points(client: TestClient):
    """1.2 Calibrate with points separated by <= 1e-6 returns HTTP 400."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    payload = {
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [0.0, 0.0, 1e-7],
        "real_distance": 1.0
    }
    res = client.post(f"/api/jobs/{job_id}/calibrate", json=payload)
    assert res.status_code == 400
    assert "too close together" in res.json()["detail"].lower()


def test_calibrate_malformed_coordinates_tuples(client: TestClient):
    """1.3 Calibrate with 2D or 4D coordinate vectors returns HTTP 422/400 validation error."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    # Point A has only 2 coordinates
    res1 = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [1.0, 2.0],
        "point_b": [1.0, 2.0, 3.0],
        "real_distance": 1.5
    })
    assert res1.status_code in [400, 422]
    assert "coordinate" in res1.text.lower() or "3-element" in res1.text.lower() or "point_a" in res1.text.lower()

    # Point B has 4 coordinates
    res2 = client.post(f"/api/jobs/{job_id}/calibrate", json={
        "point_a": [1.0, 2.0, 3.0],
        "point_b": [1.0, 2.0, 3.0, 4.0],
        "real_distance": 1.5
    })
    assert res2.status_code in [400, 422]
    assert "coordinate" in res2.text.lower() or "3-element" in res2.text.lower() or "point_b" in res2.text.lower()


def test_calibrate_non_existent_job(client: TestClient):
    """1.4 Calibrate on non-existent job ID returns HTTP 404."""
    fake_id = "11111111-2222-3333-4444-555555555555"
    payload = {
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.0, 0.0, 0.0],
        "real_distance": 1.0
    }
    res = client.post(f"/api/jobs/{fake_id}/calibrate", json=payload)
    assert res.status_code == 404
    assert f"Job {fake_id} not found" in res.json()["detail"]


def test_calibrate_negative_real_distance_handled(client: TestClient):
    """1.5 Calibrate with negative real_distance rejected with HTTP 422/400."""
    job_id = submit_job(client)
    complete_job_pipeline(job_id)

    payload = {
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.0, 0.0, 0.0],
        "real_distance": -2.0
    }
    res = client.post(f"/api/jobs/{job_id}/calibrate", json=payload)
    assert res.status_code in [400, 422]
    assert "greater than 0" in res.text.lower() or "> 0" in res.text.lower()


# ============================================================================
# Category 2: Upload, File Ingestion & Parameter Boundaries (>=5 tests)
# ============================================================================

def test_upload_exceeding_max_size_cap(client: TestClient, monkeypatch):
    """2.1 Upload exceeding SCANFORGE_MAX_UPLOAD_MB returns HTTP 413 and deletes partial file."""
    monkeypatch.setattr(settings, "SCANFORGE_MAX_UPLOAD_MB", 1)

    oversized = b"\x00" * int(1.5 * 1024 * 1024)
    files = {"file": ("oversized_video.mp4", io.BytesIO(oversized), "video/mp4")}
    data = {"scan_type": "photo", "quality": "draft"}

    res = client.post("/api/jobs", files=files, data=data)
    assert res.status_code == 413
    assert "exceeds maximum allowed upload size" in res.json()["detail"]

    # Verify no partial file remains
    stray = list(storage_service.uploads_dir.glob("**/oversized_video.mp4"))
    assert len(stray) == 0


def test_upload_missing_file_payload(client: TestClient):
    """2.2 POST /api/jobs without 'file' field returns HTTP 422 Unprocessable Entity."""
    res = client.post("/api/jobs", data={"scan_type": "photo"})
    assert res.status_code == 422


def test_upload_empty_zero_byte_file(client: TestClient):
    """2.3 Upload empty 0-byte file without crashing the server."""
    files = {"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")}
    data = {"scan_type": "photo", "quality": "draft"}
    res = client.post("/api/jobs", files=files, data=data)
    assert res.status_code in [202, 400]


def test_upload_malformed_json_options_fallback(client: TestClient):
    """2.4 Malformed JSON in 'options' gracefully falls back to empty dict."""
    files = {"file": ("test.mp4", io.BytesIO(make_dummy_mp4()), "video/mp4")}
    data = {"scan_type": "photo", "options": "{this is invalid json: definitely}"}
    res = client.post("/api/jobs", files=files, data=data)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    job = client.get(f"/api/jobs/{job_id}").json()
    assert isinstance(job["options"], dict)


def test_upload_malformed_output_formats_fallback(client: TestClient):
    """2.5 Malformed JSON in 'output_formats' gracefully falls back to ['glb', 'obj']."""
    files = {"file": ("test.mp4", io.BytesIO(make_dummy_mp4()), "video/mp4")}
    data = {"scan_type": "photo", "output_formats": "not a json list"}
    res = client.post("/api/jobs", files=files, data=data)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    job = client.get(f"/api/jobs/{job_id}").json()
    assert "glb" in job["output_formats"]
    assert "obj" in job["output_formats"]


def test_upload_unsupported_file_extension(client: TestClient):
    """2.6 Uploading invalid file extension (.sh) is rejected with HTTP 400."""
    files = {"file": ("payload.sh", io.BytesIO(b"echo test"), "text/x-sh")}
    data = {"scan_type": "photo"}
    res = client.post("/api/jobs", files=files, data=data)
    assert res.status_code == 400
    assert "allowed" in res.json()["detail"].lower() or "extension" in res.json()["detail"].lower()


# ============================================================================
# Category 3: Pagination, Query & Lifecycle Boundaries (>=5 tests)
# ============================================================================

def test_list_jobs_invalid_limit_zero_or_negative(client: TestClient):
    """3.1 GET /api/jobs with limit <= 0 returns HTTP 422 validation error."""
    res0 = client.get("/api/jobs?limit=0")
    assert res0.status_code == 422

    res_neg = client.get("/api/jobs?limit=-5")
    assert res_neg.status_code == 422


def test_list_jobs_invalid_limit_exceeding_max(client: TestClient):
    """3.2 GET /api/jobs with limit > 100 returns HTTP 422 validation error."""
    res = client.get("/api/jobs?limit=101")
    assert res.status_code == 422


def test_list_jobs_negative_offset(client: TestClient):
    """3.3 GET /api/jobs with offset < 0 returns HTTP 422 validation error."""
    res = client.get("/api/jobs?offset=-1")
    assert res.status_code == 422


def test_get_non_existent_job_returns_404(client: TestClient):
    """3.4 GET /api/jobs/{id} for non-existent job returns HTTP 404."""
    fake_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    res = client.get(f"/api/jobs/{fake_id}")
    assert res.status_code == 404
    assert f"Job {fake_id} not found" in res.json()["detail"]


def test_cancel_non_existent_job_returns_404(client: TestClient):
    """3.5 POST /api/jobs/{id}/cancel for non-existent job returns HTTP 404."""
    fake_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    res = client.post(f"/api/jobs/{fake_id}/cancel")
    assert res.status_code == 404


def test_delete_non_existent_job_returns_404(client: TestClient):
    """3.6 DELETE /api/jobs/{id} for non-existent job returns HTTP 404."""
    fake_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    res = client.delete(f"/api/jobs/{fake_id}")
    assert res.status_code == 404


# ============================================================================
# Category 4: Artifacts, Downloads & Log Retrieval Boundaries (>=5 tests)
# ============================================================================

def test_download_artifact_non_existent_job_returns_404(client: TestClient):
    """4.1 Downloading artifact for non-existent job returns HTTP 404."""
    fake_id = "deadbeef-dead-beef-dead-beefdeadbeef"
    res = client.get(f"/api/jobs/{fake_id}/download/glb")
    assert res.status_code == 404


def test_download_unsupported_format_for_existing_job_returns_404(client: TestClient):
    """4.2 Downloading non-existent format for an existing job returns HTTP 404."""
    job_id = submit_job(client, output_formats=["glb"])
    complete_job_pipeline(job_id)

    res = client.get(f"/api/jobs/{job_id}/download/unsupported_format_xyz")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_download_all_non_existent_job_returns_404(client: TestClient):
    """4.3 GET /download-all on a non-existent job returns HTTP 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    res = client.get(f"/api/jobs/{fake_id}/download-all")
    assert res.status_code == 404
    assert f"Job {fake_id} not found" in res.json()["detail"]


def test_get_job_log_missing_returns_404(client: TestClient):
    """4.4 GET /api/jobs/{id}/log on a job without a pipeline.log file returns HTTP 404."""
    job_id = submit_job(client)
    res = client.get(f"/api/jobs/{job_id}/log")
    assert res.status_code == 404
    assert "Log file not found" in res.json()["detail"]


def test_get_job_cut_image_missing_returns_404(client: TestClient):
    """4.5 GET /api/jobs/{id}/cuts/{filename} for non-existent cut image returns HTTP 404."""
    job_id = submit_job(client)
    res = client.get(f"/api/jobs/{job_id}/cuts/non_existent_frame.jpg")
    assert res.status_code == 404
