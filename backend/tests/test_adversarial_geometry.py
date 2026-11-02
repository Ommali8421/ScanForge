"""
Adversarial Geometry & Math Stress Testing Suite
Challenger 1 (Replacement) — Milestones M1 & M2

Tests edge cases, boundary conditions, and mathematical singularities across:
1. floor_align.py (antiparallel vectors, extreme offsets, zero floor inliers, gravity fallback grounding)
2. cleanup.py (planar trajectories, zero vertical/horizontal span, negative margins)
3. plane_repair.py (NoneType handling, zero dominant planes, weak wall filtering)
4. decimate.py (plane spike exemption, zero-area triangles, aspect ratio thresholds)
"""

import json
import math
import tempfile
from pathlib import Path
import numpy as np
import pytest
import trimesh
import open3d as o3d

from app.pipelines.base import JobContext, CancelToken
from app.pipelines.mesh.floor_align import (
    compute_floor_alignment_transform,
    apply_alignment_and_scale_to_mesh,
    FloorAlignAndScaleStage,
)
from app.pipelines.mesh.cleanup import MeshCleanupStage
from app.pipelines.mesh.plane_repair import (
    PlaneRepairStage,
    line_intersection_of_two_planes,
    smoothstep,
)
from app.pipelines.mesh.decimate import DecimateStage


# ============================================================================
# 1. FLOOR_ALIGN.PY ADVERSARIAL TESTS
# ============================================================================

def test_floor_align_antiparallel_y_up():
    """Verify antiparallel normal [0, -1, 0] with Y-up target produces valid rotation."""
    R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
        floor_normal=np.array([0.0, -1.0, 0.0]),
        floor_d=1.5,
        cam_centroid=np.array([0.0, 0.5, 0.0]),
        target_up=np.array([0.0, 1.0, 0.0]),
        u_grav=np.array([0.0, -1.0, 0.0]),
    )
    assert not np.isnan(R_total).any()
    det = np.linalg.det(R_total)
    assert np.isclose(det, 1.0, atol=1e-5), f"Determinant is {det}, expected 1.0"
    assert np.allclose(R_total @ R_total.T, np.eye(3), atol=1e-5), "Matrix is not orthogonal"
    transformed_n = R_total @ fn_oriented
    assert np.allclose(transformed_n, np.array([0.0, 1.0, 0.0]), atol=1e-4)


def test_floor_align_antiparallel_z_up():
    """
    Verify antiparallel normal [0, 0, -1] with Z-up target produces valid rotation.
    ADVERSARIAL STRESS TEST: Checks for singularity/rank-deficiency in Z-up branch.
    """
    R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
        floor_normal=np.array([0.0, 0.0, -1.0]),
        floor_d=1.5,
        cam_centroid=np.array([0.0, 0.0, 0.5]),
        target_up=np.array([0.0, 0.0, 1.0]),
        u_grav=np.array([0.0, 0.0, -1.0]),
    )
    assert not np.isnan(R_total).any(), "Matrix contains NaN"
    det = float(np.linalg.det(R_total))
    is_orthogonal = bool(np.allclose(R_total @ R_total.T, np.eye(3), atol=1e-5))

    # Test transformation on a 3D volume
    test_vec = np.array([1.0, 2.0, 3.0])
    transformed_vec = R_total @ test_vec

    assert is_orthogonal, (
        f"CRITICAL BUG: R_total is not orthogonal when target_up is Z and normal is antiparallel! "
        f"R_total:\n{R_total}\nR @ R.T:\n{R_total @ R_total.T}"
    )
    assert np.isclose(det, 1.0, atol=1e-4), (
        f"CRITICAL BUG: Determinant is {det} (expected 1.0). "
        f"Singular matrix collapses geometry into 2D plane!"
    )
    assert np.isclose(np.linalg.norm(transformed_vec), np.linalg.norm(test_vec), atol=1e-4), (
        f"Vector length changed from {np.linalg.norm(test_vec)} to {np.linalg.norm(transformed_vec)}"
    )


def test_floor_align_zero_floor_normal_fallback():
    """Verify zero-length floor normal [0, 0, 0] does not trigger division by zero or NaN."""
    R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
        floor_normal=np.array([0.0, 0.0, 0.0]),
        floor_d=0.0,
        cam_centroid=np.array([0.0, 1.0, 0.0]),
        target_up=np.array([0.0, 1.0, 0.0]),
    )
    assert not np.isnan(R_total).any()
    assert np.allclose(R_total, np.eye(3), atol=1e-5)


def test_floor_align_extreme_offset_stability():
    """Verify numerical stability under extreme coordinate offsets (10,000 km)."""
    box = trimesh.creation.box(extents=(10, 10, 10))
    box.apply_translation([1e7, 1e7, 1e7])

    R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
        floor_normal=np.array([0.0, 1.0, 0.0]),
        floor_d=-1e7,
        cam_centroid=np.array([1e7, 1e7 + 2.0, 1e7]),
        target_up=np.array([0.0, 1.0, 0.0]),
    )
    transformed, meta = apply_alignment_and_scale_to_mesh(
        mesh=box,
        R_total=R_total,
        fn_oriented=fn_oriented,
        fd_oriented=fd_oriented,
        diag=box.bounding_box.primitive.extents.max(),
        scale=1.0,
        target_up=np.array([0.0, 1.0, 0.0]),
    )
    assert not np.isnan(meta["bounds_min"]).any()
    assert not np.isinf(meta["bounds_min"]).any()
    # Centered at (0, 0) horizontally
    assert np.isclose(meta["bounds_min"][0], -5.0, atol=1e-3)
    assert np.isclose(meta["bounds_max"][0], 5.0, atol=1e-3)


def test_floor_align_zero_floor_inliers_fallback():
    """Verify floor leveling when 0 vertices are within floor plane threshold."""
    box = trimesh.creation.box(extents=(2, 2, 2))
    # Plane far away from the box -> 0 inliers
    target_up = np.array([0.0, 1.0, 0.0])
    transformed, meta = apply_alignment_and_scale_to_mesh(
        mesh=box,
        R_total=np.eye(3),
        fn_oriented=np.array([0.0, 1.0, 0.0]),
        fd_oriented=50.0,
        diag=box.bounding_box.primitive.extents.max(),
        scale=1.0,
        target_up=target_up,
    )
    assert meta["floor_inliers_count"] == 0
    # Fallback uses -fd * fn
    assert not np.isnan(meta["Y_floor_offset"])
    assert np.isclose(meta["Y_floor_offset"], -50.0, atol=1e-5)


def test_floor_align_gravity_fallback_grounding():
    """Verify gravity fallback (chosen_floor_plane is None) grounds 5th-percentile vertex at Y=0.000."""
    np.random.seed(123)
    verts = np.random.uniform(-4, 4, size=(500, 3))
    verts[:, 1] = np.random.uniform(-2.5, 3.5, size=500)
    faces = np.arange(498).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)

    target_up = np.array([0.0, 1.0, 0.0])
    u_grav = np.array([0.0, 1.0, 0.0])

    R_total, _, _ = compute_floor_alignment_transform(
        floor_normal=u_grav,
        floor_d=0.0,
        cam_centroid=np.array([0.0, 0.0, 0.0]),
        target_up=target_up,
        u_grav=u_grav,
    )

    transformed, meta = apply_alignment_and_scale_to_mesh(
        mesh=mesh,
        R_total=R_total,
        fn_oriented=None,  # Gravity fallback flag
        fd_oriented=0.0,
        diag=mesh.bounding_box.primitive.extents.max(),
        scale=1.0,
        target_up=target_up,
    )
    p5_y = np.percentile(transformed.vertices[:, 1], 5)
    assert np.isclose(p5_y, 0.0, atol=1e-5), f"5th percentile vertex Y is {p5_y}, expected 0.000"


# ============================================================================
# 2. CLEANUP.PY ADVERSARIAL TESTS
# ============================================================================

def test_cleanup_planar_trajectory_zero_vertical_span():
    """Verify planar trajectory (vertical camera span = 0) does not clip floor or high ceiling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        # Create a room mesh: floor at Y=0, ceiling at Y=6.0, walls between X,Z in [0, 10]
        # Cameras walk at Y=1.5 with vertical span = 0
        floor_mesh = trimesh.creation.box(extents=(10, 0.1, 8))
        floor_mesh.apply_translation([5.0, 0.0, 4.0])
        ceil_mesh = trimesh.creation.box(extents=(10, 0.1, 8))
        ceil_mesh.apply_translation([5.0, 6.0, 4.0])
        room = trimesh.util.concatenate([floor_mesh, ceil_mesh])
        (td / "scene_dense_mesh.ply").write_bytes(trimesh.exchange.ply.export_ply(room))

        # Write camera poses with zero vertical span
        sparse_dir = td / "sparse_txt"
        sparse_dir.mkdir(parents=True, exist_ok=True)
        # images.txt: 4 cameras at Y=1.5
        cams_text = "# Image list\n"
        for i, (x, z) in enumerate([(1.0, 1.0), (9.0, 1.0), (9.0, 7.0), (1.0, 7.0)]):
            # QW, QX, QY, QZ, TX, TY, TZ (Identity rotation, center = -t)
            cams_text += f"{i+1} 1.0 0.0 0.0 0.0 {-x} -1.5 {-z} 1 frame_{i+1:04d}.jpg\n\n"
        (sparse_dir / "images.txt").write_text(cams_text)

        ctx = JobContext(
            job_id="test-cleanup-zero-vert",
            workdir=td,
            params={},
            cancel_token=CancelToken(),
            progress_cb=lambda *args: None,
            log_cb=lambda *args: None,
        )
        stage = MeshCleanupStage()
        res = stage.run(ctx)
        assert res.success

        cleaned = trimesh.load(str(td / "mesh_cleaned.ply"), process=False)
        # Ceiling at Y=6.0 and floor at Y=0.0 must be preserved
        assert cleaned.vertices[:, 1].max() >= 5.9, "Ceiling was clipped by planar trajectory envelope!"
        assert cleaned.vertices[:, 1].min() <= 0.1, "Floor was clipped by planar trajectory envelope!"


def test_cleanup_degenerate_cams_under_four():
    """Verify that having fewer than 4 cameras safely skips bounding envelope without crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        box = trimesh.creation.box(extents=(2, 2, 2))
        (td / "scene_dense_mesh.ply").write_bytes(trimesh.exchange.ply.export_ply(box))

        sparse_dir = td / "sparse_txt"
        sparse_dir.mkdir(parents=True, exist_ok=True)
        # Only 2 cameras
        cams_text = "1 1.0 0.0 0.0 0.0 0.0 0.0 0.0 1 f1.jpg\n\n2 1.0 0.0 0.0 0.0 1.0 0.0 0.0 1 f2.jpg\n\n"
        (sparse_dir / "images.txt").write_text(cams_text)

        ctx = JobContext(
            job_id="test-cleanup-few-cams",
            workdir=td,
            params={},
            cancel_token=CancelToken(),
            progress_cb=lambda *args: None,
            log_cb=lambda *args: None,
        )
        stage = MeshCleanupStage()
        res = stage.run(ctx)
        assert res.success
        assert res.metadata["cleaned_faces"] > 0


# ============================================================================
# 3. PLANE_REPAIR.PY ADVERSARIAL TESTS
# ============================================================================

def test_plane_repair_none_floor_and_zero_dominant_planes():
    """Verify PlaneRepairStage handles chosen_floor_plane is None and 0 dominant planes gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        box = trimesh.creation.box(extents=(2, 2, 2))
        (td / "mesh_cleaned.ply").write_bytes(trimesh.exchange.ply.export_ply(box))

        ra_data = {
            "scene_diagonal": 3.46,
            "chosen_floor_plane": None,
            "wall_planes": [],
            "total_dominant_planes_detected": 0,
        }
        (td / "room_analysis.json").write_text(json.dumps(ra_data))

        ctx = JobContext(
            job_id="test-plane-repair-none",
            workdir=td,
            params={},
            cancel_token=CancelToken(),
            progress_cb=lambda *args: None,
            log_cb=lambda *args: None,
        )
        stage = PlaneRepairStage()
        res = stage.run(ctx)
        assert res.success
        assert res.metadata["vertices_snapped"] == 0
        assert res.metadata["dropped_below_floor_faces"] == 0
        assert res.metadata["dropped_outside_wall_faces"] == 0
        assert (td / "mesh_repaired.ply").exists()


def test_plane_repair_weak_walls_suppressed():
    """Verify wall pruning is safely suppressed when fewer than 2 strong walls exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        box = trimesh.creation.box(extents=(2, 2, 2))
        (td / "mesh_cleaned.ply").write_bytes(trimesh.exchange.ply.export_ply(box))

        ra_data = {
            "scene_diagonal": 3.46,
            "chosen_floor_plane": None,
            # Only 1 wall with 500 inliers (< 1000 threshold)
            "wall_planes": [{"normal": [1.0, 0.0, 0.0], "d": 1.0, "inliers": 500}],
            "total_dominant_planes_detected": 1,
        }
        (td / "room_analysis.json").write_text(json.dumps(ra_data))

        ctx = JobContext(
            job_id="test-plane-repair-weak-walls",
            workdir=td,
            params={},
            cancel_token=CancelToken(),
            progress_cb=lambda *args: None,
            log_cb=lambda *args: None,
        )
        stage = PlaneRepairStage()
        res = stage.run(ctx)
        assert res.success
        assert res.metadata["dropped_outside_wall_faces"] == 0


def test_line_intersection_parallel_planes():
    """Verify line intersection of parallel planes returns valid fallback without zero-division."""
    p_line, dir_line = line_intersection_of_two_planes(
        n1=np.array([0.0, 1.0, 0.0]), d1=1.0,
        n2=np.array([0.0, 1.0, 0.0]), d2=2.0
    )
    assert not np.isnan(p_line).any()
    assert not np.isnan(dir_line).any()
    assert np.isclose(np.linalg.norm(dir_line), 1.0)


# ============================================================================
# 4. DECIMATE.PY ADVERSARIAL TESTS
# ============================================================================

def test_decimate_plane_spike_exemption():
    """
    Verify post-decimation spike filter exempts triangles lying on confirmed RANSAC planes.
    Triangles on plane with edge > 4.5x median must NOT be pruned unless > 8.0x median.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        # Create a mesh with a dense cluster and one large triangle lying exactly on floor plane Y=0
        # Dense cluster around origin (makes median edge length ~0.1m)
        box = trimesh.creation.box(extents=(0.5, 0.5, 0.5))
        # Add a large planar triangle on Y=0 with edge length = 0.6m (6x median)
        v_large = np.array([
            [1.0, 0.0, 1.0],
            [1.6, 0.0, 1.0],
            [1.0, 0.0, 1.6],
        ])
        f_large = np.array([[0, 1, 2]])
        tri_mesh = trimesh.Trimesh(vertices=v_large, faces=f_large, process=False)
        combined = trimesh.util.concatenate([box, tri_mesh])
        (td / "mesh_repaired.ply").write_bytes(trimesh.exchange.ply.export_ply(combined))

        # room_analysis defining floor plane at Y=0: n=[0, 1, 0], d=0.0
        ra_data = {
            "scene_diagonal": 5.0,
            "chosen_floor_plane": {"normal": [0.0, 1.0, 0.0], "d": 0.0, "inliers": 2000},
            "wall_planes": [],
        }
        (td / "room_analysis.json").write_text(json.dumps(ra_data))

        ctx = JobContext(
            job_id="test-decimate-plane-exemption",
            workdir=td,
            params={"quality": "standard", "options": {"poly_target": 10000}},
            cancel_token=CancelToken(),
            progress_cb=lambda *args: None,
            log_cb=lambda *args: None,
        )
        stage = DecimateStage()
        res = stage.run(ctx)
        assert res.success

        dec_mesh = trimesh.load(str(td / "mesh_decimated.ply"), process=False)
        # Check if the planar vertices are preserved
        has_planar_v = np.any(np.isclose(dec_mesh.vertices[:, 0], 1.6, atol=0.05))
        assert has_planar_v, "Planar triangle with edge length 6x median was improperly pruned!"


def test_decimate_zero_area_degenerate_triangle():
    """Verify zero-area triangle does not crash aspect ratio calculation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        # Create a mesh with collinear vertices (area = 0.0)
        v = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],  # Collinear!
            [0.0, 1.0, 0.0],
        ])
        f = np.array([
            [0, 1, 2],  # Zero area
            [0, 1, 3],  # Valid area
        ])
        m = trimesh.Trimesh(vertices=v, faces=f, process=False)
        (td / "mesh_repaired.ply").write_bytes(trimesh.exchange.ply.export_ply(m))

        ctx = JobContext(
            job_id="test-decimate-zero-area",
            workdir=td,
            params={"quality": "standard", "options": {"poly_target": 100}},
            cancel_token=CancelToken(),
            progress_cb=lambda *args: None,
            log_cb=lambda *args: None,
        )
        stage = DecimateStage()
        res = stage.run(ctx)
        assert res.success
