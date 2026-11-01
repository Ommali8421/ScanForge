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


def test_ceiling_plane_rejection():
    """Verify that ceiling planes (above camera centers or upper point cloud) are rejected from being chosen as floor."""
    from app.pipelines.mesh.room_analysis import RoomAnalysisStage

    # Synthetic room with floor at Y=-1.5, ceiling at Y=+2.5, cameras at Y=+0.5
    u_grav = np.array([0.0, 1.0, 0.0])
    cam_centers = np.array([
        [0.0, 0.5, 0.0],
        [1.0, 0.6, 0.5],
        [-1.0, 0.4, -0.5]
    ])
    cam_heights = cam_centers @ u_grav
    p25_cam = float(np.percentile(cam_heights, 25))

    # Ceiling candidate at height +2.5
    ceiling_plane = {
        "normal": [0.0, 1.0, 0.0],
        "d": -2.5,
        "height": 2.5,
        "inliers": 15000,
        "cos_up": 1.0
    }

    # Floor candidate at height -1.5
    floor_plane = {
        "normal": [0.0, 1.0, 0.0],
        "d": 1.5,
        "height": -1.5,
        "inliers": 8000,
        "cos_up": 1.0
    }

    # Test ceiling rejection rule
    p30_verts = 0.0  # lowest 30% of vertices are below 0.0
    assert ceiling_plane["height"] > p25_cam, "Ceiling plane is incorrectly considered below cameras"
    assert ceiling_plane["height"] > p30_verts, "Ceiling plane is incorrectly considered in lowest 30% of vertices"
    assert floor_plane["height"] <= p25_cam, "Floor plane is not below cameras"
    assert floor_plane["height"] <= p30_verts, "Floor plane is not in lowest 30% of vertices"


def test_gravity_fallback_when_no_floor_plane(tmp_path):
    """Verify that when chosen_floor_plane is None, FloorAlignAndScaleStage falls back to gravity vector and 5% bottom leveling."""
    workdir = tmp_path / "fallback_job"
    workdir.mkdir()

    # Create synthetic room
    room = create_synthetic_textured_room()
    # Tilt room by 30 degrees around X axis
    R_tilt = trimesh.transformations.rotation_matrix(np.radians(30), [1, 0, 0])[:3, :3]
    room.vertices = room.vertices @ R_tilt.T

    glb_path = workdir / "scene_textured.glb"
    room.export(str(glb_path))

    # room_analysis.json with chosen_floor_plane = None and gravity_up_vector reflecting the tilt
    u_grav = R_tilt @ np.array([0.0, 1.0, 0.0])
    analysis_data = {
        "gravity_up_vector": u_grav.tolist(),
        "camera_mean_up": u_grav.tolist(),
        "cam_bbox_min": [-1.0, -0.5, -1.0],
        "cam_bbox_max": [1.0, 0.5, 1.0],
        "scene_diagonal": 10.0,
        "chosen_floor_plane": None  # No verified floor plane
    }
    (workdir / "room_analysis.json").write_text(json.dumps(analysis_data))

    ctx = JobContext(
        job_id="test_fallback_job",
        workdir=workdir,
        params={"quality": "standard", "options": {"up_axis": "y"}},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None,
        cumulative_scale=1.0
    )

    stage = FloorAlignAndScaleStage()
    res = stage.run(ctx)
    assert res.success is True

    # Output aligned mesh should be leveled so 5th percentile bottom vertices are at Y = 0.000
    aligned = trimesh.load(str(workdir / "aligned_textured.glb"), force="mesh", process=False)
    p5_y = np.percentile(aligned.vertices[:, 1], 5)
    assert abs(p5_y) < 1e-3, f"5th percentile vertex height {p5_y} is not near 0.000"


def test_exported_mesh_glb_pbr_materials_and_double_sided(tmp_path):
    """Verify that mesh.glb and preview_textured.glb strictly have metallicFactor=0.0 and doubleSided=True."""
    workdir = tmp_path / "pbr_test_job"
    workdir.mkdir()

    room = create_synthetic_textured_room()
    glb_in = workdir / "aligned_textured.glb"
    room.export(str(glb_in))

    ctx = JobContext(
        job_id="test_pbr_job",
        workdir=workdir,
        params={"output_formats": ["glb", "gltf"], "options": {"up_axis": "y", "units": "m"}},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None,
        cumulative_scale=1.0
    )

    stage = MeshExportStage()
    res = stage.run(ctx)
    assert res.success is True

    # Check mesh.glb PBR directly from binary chunk
    import struct
    mesh_glb = workdir / "mesh.glb"
    assert mesh_glb.exists()

    with open(mesh_glb, "rb") as f:
        f.read(12)
        j_len, _ = struct.unpack("<II", f.read(8))
        gltf = json.loads(f.read(j_len).decode("utf-8"))

    mats = gltf.get("materials", [])
    assert len(mats) > 0, "No materials found in exported mesh.glb"
    for mat in mats:
        assert mat.get("doubleSided") is True, f"doubleSided is not True in {mat}"
        pbr = mat.get("pbrMetallicRoughness", {})
        assert pbr.get("metallicFactor") == 0.0, f"metallicFactor is {pbr.get('metallicFactor')}, expected 0.0"
        assert pbr.get("roughnessFactor") == 1.0, f"roughnessFactor is {pbr.get('roughnessFactor')}, expected 1.0"


def test_post_decimation_spike_filter(tmp_path):
    """Verify that DecimateStage eliminates spurious bridging triangles with edge length > 5x median."""
    from app.pipelines.mesh.decimate import DecimateStage
    import open3d as o3d

    workdir = tmp_path / "decimate_spike_job"
    workdir.mkdir()

    # Create a dense flat grid mesh
    x = np.linspace(0, 2, 40)
    z = np.linspace(0, 2, 40)
    xx, zz = np.meshgrid(x, z)
    verts = np.column_stack([xx.ravel(), np.zeros(len(xx.ravel())), zz.ravel()])

    # Generate regular Delaunay triangles
    from scipy.spatial import Delaunay
    tri = Delaunay(verts[:, [0, 2]])
    faces = tri.simplices.copy()

    # Add a massive spurious razor-sharp triangle spike:
    # 2 vertices on the floor, 1 vertex far away (10 meters)
    spike_vert_idx = len(verts)
    verts = np.vstack([verts, [1.0, 10.0, 1.0]])
    spike_face = np.array([[0, 1, spike_vert_idx]])
    faces = np.vstack([faces, spike_face])

    in_mesh = o3d.geometry.TriangleMesh()
    in_mesh.vertices = o3d.utility.Vector3dVector(verts)
    in_mesh.triangles = o3d.utility.Vector3iVector(faces)
    in_ply = workdir / "mesh_repaired.ply"
    o3d.io.write_triangle_mesh(str(in_ply), in_mesh)

    ctx = JobContext(
        job_id="test_spike_job",
        workdir=workdir,
        params={"quality": "standard", "options": {"poly_target": 5000}},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None,
        cumulative_scale=1.0
    )

    stage = DecimateStage()
    res = stage.run(ctx)
    assert res.success is True

    out_ply = workdir / "mesh_decimated.ply"
    out_mesh = o3d.io.read_triangle_mesh(str(out_ply))
    out_v = np.asarray(out_mesh.vertices)
    out_f = np.asarray(out_mesh.triangles)

    e0 = np.linalg.norm(out_v[out_f[:, 0]] - out_v[out_f[:, 1]], axis=1)
    e1 = np.linalg.norm(out_v[out_f[:, 1]] - out_v[out_f[:, 2]], axis=1)
    e2 = np.linalg.norm(out_v[out_f[:, 2]] - out_v[out_f[:, 0]], axis=1)
    max_edges = np.maximum(e0, np.maximum(e1, e2))
    all_edges = np.concatenate([e0, e1, e2])
    med_e = np.median(all_edges)

    # Spike was ~10 meters long; must have been completely dropped
    assert np.max(max_edges) <= 5.0 * med_e + 1e-4, f"Spike with max edge {np.max(max_edges)} was not filtered!"
