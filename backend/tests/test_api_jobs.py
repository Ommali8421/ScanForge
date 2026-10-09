"""
Tests for Job APIs, Lifecycle, and Calibration
"""

import io
from fastapi.testclient import TestClient
from app.main import app
from app.services.job_service import get_job

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
    assert data["version"] == "0.1.0"


def test_create_and_query_job():
    # Mock video file upload
    file_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 500
    files = {"file": ("room_tour.mp4", io.BytesIO(file_bytes), "video/mp4")}
    data = {
        "scan_type": "photo",
        "quality": "standard",
        "output_formats": '["glb", "obj"]',
        "options": '{"include_mesh": true}'
    }

    response = client.post("/api/jobs", files=files, data=data)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert job_id is not None

    # Retrieve job details
    get_res = client.get(f"/api/jobs/{job_id}")
    assert get_res.status_code == 200
    job_data = get_res.json()
    assert job_data["id"] == job_id
    assert job_data["scan_type"] == "photo"
    assert job_data["cumulative_scale"] == 1.0


def test_cumulative_scale_calibration():
    # Create job
    file_bytes = b"\x00" * 200
    files = {"file": ("capture.zip", io.BytesIO(file_bytes), "application/zip")}
    res = client.post("/api/jobs", files=files, data={"scan_type": "photo"})
    job_id = res.json()["job_id"]

    # Calibrate scale: points at distance 2.0, real distance 3.0 -> factor 1.5
    cal_payload = {
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [2.0, 0.0, 0.0],
        "real_distance": 3.0
    }
    cal_res = client.post(f"/api/jobs/{job_id}/calibrate", json=cal_payload)
    assert cal_res.status_code == 202
    data = cal_res.json()
    assert data["measured_distance"] == 2.0
    assert data["applied_factor"] == 1.5
    assert data["cumulative_scale"] == 1.5

    # Second calibration step: measured 1.5, real 1.5 -> cumulative remains 1.5
    cal_payload_2 = {
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.0, 0.0, 0.0],
        "real_distance": 2.0
    }
    cal_res_2 = client.post(f"/api/jobs/{job_id}/calibrate", json=cal_payload_2)
    assert cal_res_2.status_code == 202
    data_2 = cal_res_2.json()
    assert data_2["applied_factor"] == 2.0
    # Amendment 3: New factor multiplied into current scale (1.5 * 2.0 = 3.0)
    assert data_2["cumulative_scale"] == 3.0
