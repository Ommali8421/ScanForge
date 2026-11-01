"""
Unit & Roundtrip Tests for Phase 3 (Floor Alignment, Scale Calibration, Exporters & Quality Report)
"""

import io
import json
import math
import zipfile
from pathlib import Path
import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.main import app
from app.pipelines.base import JobContext, CancelToken
from app.pipelines.mesh.canonical import CanonicalMesh
from app.pipelines.mesh.floor_align import (
    compute_floor_alignment_transform,
    apply_alignment_and_scale_to_mesh,
    FloorAlignAndScaleStage
)
from app.pipelines.mesh.exporters import (
    apply_user_transform_for_export,
    MeshExportStage
)
from app.pipelines.mesh.quality_report import (
    generate_quality_report_dict,
    QualityReportStage
)

client = TestClient(app)


def create_synthetic_textured_room() -> trimesh.Trimesh:
    """Creates a synthetic textured interior room mesh with a floor, 4 walls, and UVs."""
    # Create simple box with open ceiling
    box = trimesh.creation.box(extents=[4.0, 2.5, 5.0])
    # Give it synthetic UVs and image texture
    from PIL import Image
    img = Image.new("RGB", (64, 64), color=(180, 170, 160))
    uvs = np.zeros((len(box.vertices), 2), dtype=np.float32)
    uvs[:, 0] = (box.vertices[:, 0] + 2.0) / 4.0
    uvs[:, 1] = (box.vertices[:, 2] + 2.5) / 5.0

    visual = trimesh.visual.texture.TextureVisuals(uv=uvs, image=img)
    box.visual = visual
    return box


def test_floor_align_antiparallel_singularity_guard():
    """Verify that antiparallel floor normal (0, -1, 0) does not produce NaN or zero division."""
    fn_antiparallel = np.array([0.0, -1.0, 0.0])
    fd = 1.5
    cam_centroid = np.array([0.0, 0.5, 0.0])  # Camera is above the floor
    target_up = np.array([0.0, 1.0, 0.0])

    R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
        floor_normal=fn_antiparallel,
        floor_d=fd,
        cam_centroid=cam_centroid,
        target_up=target_up
    )

    # Must be valid 3x3 orthonormal matrix
    assert not np.isnan(R_total).any(), "Rotation matrix contains NaN"
    assert np.allclose(R_total @ R_total.T, np.eye(3), atol=1e-5), "Rotation matrix is not orthogonal"
    # When applied to fn_oriented, should point +Y
    transformed_n = R_total @ fn_oriented
    assert np.allclose(transformed_n, target_up, atol=1e-4), f"Transformed normal {transformed_n} does not match {target_up}"


def test_floor_align_normal_sign_orientation():
    """Verify that inverted floor normals (pointing downward away from room) are flipped to point into the room."""
    # Floor at Y = -1.5, normal pointing downwards (0, -1, 0) away from cameras at Y = +0.5
    fn_inverted = np.array([0.0, -1.0, 0.0])
    fd = -1.5  # n . x + d = 0 -> -y - 1.5 = 0 -> y = -1.5
    cam_centroid = np.array([0.0, 0.5, 0.0])

    R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
        floor_normal=fn_inverted,
        floor_d=fd,
        cam_centroid=cam_centroid
    )

    # Floor point is [0, -1.5, 0], vector to cam is [0, 2.0, 0]
    # Oriented normal must have positive dot product with cam_vec
    floor_pt = -fd_oriented * fn_oriented
    assert np.dot(fn_oriented, cam_centroid - floor_pt) > 0, "Floor normal does not point towards camera centroid"


def test_floor_align_robust_y0_leveling_and_scale():
    """Verify that floor inlier median levels floor to Y=0.000 and applies physical scale."""
    room = create_synthetic_textured_room()
    # Add noisy subfloor vertices at Y = -1.5
    noisy_verts = np.array([
        [0.0, -1.55, 0.0],
        [0.2, -1.48, 0.1]
    ])
    all_verts = np.vstack([room.vertices, noisy_verts])
    faces = np.vstack([room.faces, np.array([[len(room.vertices), len(room.vertices) + 1, 0]])])
    test_mesh = trimesh.Trimesh(vertices=all_verts, faces=faces, process=False)

    # Floor is at Y = -1.25 (half of 2.5 height)
    fn = np.array([0.0, 1.0, 0.0])
    fd = 1.25
    cam_centroid = np.array([0.0, 0.0, 0.0])

    R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
        floor_normal=fn,
        floor_d=fd,
        cam_centroid=cam_centroid
    )

    scale = 2.0
    transformed, meta = apply_alignment_and_scale_to_mesh(
        mesh=test_mesh,
        R_total=R_total,
        fn_oriented=fn_oriented,
        fd_oriented=fd_oriented,
        diag=10.0,
        scale=scale
    )

    # Verify floor inlier vertices (original Y = -1.25) landed precisely at Y = 0.000
    floor_inliers = transformed.vertices[:len(room.vertices)][test_mesh.vertices[:len(room.vertices), 1] < -1.20]
    assert np.allclose(floor_inliers[:, 1], 0.0, atol=1e-4), "Floor inliers did not land at Y = 0.000!"
    # Verify the noisy subfloor vertex is below Y=0
    noisy_transformed = transformed.vertices[len(room.vertices):]
    assert (noisy_transformed[:, 1] < 0.0).all(), "Noisy subfloor vertex floated above Y=0!"


def test_zero_retexturing_uv_bitwise_preservation():
    """Verify that alignment and scaling preserve UV coordinates bitwise."""
    room = create_synthetic_textured_room()
    orig_uvs = np.array(room.visual.uv, copy=True)

    R_total = np.eye(3)
    transformed, _ = apply_alignment_and_scale_to_mesh(
        mesh=room,
        R_total=R_total,
        fn_oriented=np.array([0.0, 1.0, 0.0]),
        fd_oriented=0.0,
        diag=10.0,
        scale=1.75
    )

    trans_uvs = np.array(transformed.visual.uv)
    assert np.array_equal(orig_uvs, trans_uvs), "UV texture coordinates were modified during alignment/scaling!"


def test_exporter_obj_zip_completeness(tmp_path):
    """Verify that MeshExportStage creates a valid mesh_obj.zip containing .obj, .mtl, and image."""
    room = create_synthetic_textured_room()
    workdir = tmp_path / "job_export_test"
    workdir.mkdir()

    # Save aligned_textured.glb
    glb_path = workdir / "aligned_textured.glb"
    room.export(str(glb_path))

    ctx = JobContext(
        job_id="test_export_job",
        workdir=workdir,
        params={
            "output_formats": ["glb", "obj", "ply", "stl", "xyz"],
            "options": {"up_axis": "y", "units": "m"}
        },
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None,
        cumulative_scale=1.0
    )

    stage = MeshExportStage()
    res = stage.run(ctx)
    assert res.success is True

    # Verify mesh_obj.zip exists and contains .obj and .mtl
    obj_zip = workdir / "mesh_obj.zip"
    assert obj_zip.exists()
    with zipfile.ZipFile(obj_zip, "r") as zf:
        namelist = zf.namelist()
        assert "mesh.obj" in namelist, "mesh.obj missing from ZIP"
        assert any(n.endswith(".mtl") for n in namelist), ".mtl missing from ZIP"

    # Verify mesh.ply, mesh.stl, mesh.xyz exist
    assert (workdir / "mesh.ply").exists()
    assert (workdir / "mesh.stl").exists()
    assert (workdir / "mesh.xyz").exists()


def test_quality_report_schema_and_uncalibrated_badge():
    """Verify that QualityReportStage emits all docs/API.md and Phase 3 fields."""
    room = create_synthetic_textured_room()
    report = generate_quality_report_dict(
        mesh=room,
        cumulative_scale=1.0,
        up_axis="y",
        is_calibrated=False
    )

    # Required API.md fields
    assert "vertex_count" in report
    assert "face_count" in report
    assert "hole_count" in report
    assert "dimensions_meters" in report
    assert "length" in report["dimensions_meters"]
    assert "width" in report["dimensions_meters"]
    assert "height" in report["dimensions_meters"]
    assert "floor_area_sqm" in report
    assert "cumulative_scale" in report
    assert "up_axis" in report

    # Mandatory Phase 3 fields
    assert "is_calibrated" in report
    assert report["is_calibrated"] is False
    assert "is_watertight" in report
    assert "quality_grade" in report


def test_api_calibrate_sequential_non_compounding(tmp_path):
    """Verify that POST /api/jobs/{id}/calibrate computes non-compounding scale and responds with 202."""
    # Create mock job via API
    file_bytes = b"\x00" * 200
    files = {"file": ("capture.zip", io.BytesIO(file_bytes), "application/zip")}
    create_res = client.post("/api/jobs", files=files, data={"scan_type": "photo"})
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    # First calibration: measured distance 2.0 -> real distance 3.0 (factor 1.5)
    cal1_res = client.post(
        f"/api/jobs/{job_id}/calibrate",
        json={"point_a": [0.0, 0.0, 0.0], "point_b": [2.0, 0.0, 0.0], "real_distance": 3.0}
    )
    assert cal1_res.status_code == 202
    data1 = cal1_res.json()
    assert data1["applied_factor"] == 1.5
    assert data1["cumulative_scale"] == 1.5

    # Second calibration: measured distance 1.0 -> real distance 2.0 (factor 2.0)
    # Cumulative scale must equal 1.5 * 2.0 = 3.0
    cal2_res = client.post(
        f"/api/jobs/{job_id}/calibrate",
        json={"point_a": [0.0, 0.0, 0.0], "point_b": [1.0, 0.0, 0.0], "real_distance_m": 2.0}
    )
    assert cal2_res.status_code == 202
    data2 = cal2_res.json()
    assert data2["applied_factor"] == 2.0
    assert data2["cumulative_scale"] == 3.0

    # Verify GET /api/jobs/{id}/report reflects calibrated state
    rep_res = client.get(f"/api/jobs/{job_id}/report")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data["cumulative_scale"] == 3.0
    assert rep_data["is_calibrated"] is True
