"""
Tests for capabilities endpoint and format matrix
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_capabilities_structure():
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    data = response.json()

    assert data["engine"] in ["mock", "real"]
    assert "format_matrix" in data
    assert "photo" in data["format_matrix"]
    assert "gaussian_splat" in data["format_matrix"]
    assert "limits" in data
    assert data["limits"]["max_upload_mb"] > 0


def test_converter_detection_disables_fbx_if_blender_missing():
    response = client.get("/api/capabilities")
    data = response.json()
    converters = data["runtime_converters"]

    # Amendment 4: If Blender is missing, FBX/USDZ must be disabled
    if not converters["blender"]:
        assert converters["fbx_supported"] is False
        assert converters["usdz_supported"] is False
        assert "fbx" not in data["format_matrix"]["photo"]
        assert "usdz" not in data["format_matrix"]["photo"]
