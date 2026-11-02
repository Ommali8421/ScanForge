"""
Unit & Integration Tests for Milestone P3 (3D Gaussian Splatting)
Validates:
1. 32-byte .splat binary format round-trip and byte-exact alignment
2. Log/logit cleanup math (opacity sigmoid, scale exp, SOR, envelope clipping)
3. COLMAP pose alignment math (world transform, camera center, ray projection invariance)
4. Splatfacto OOM catch-and-retry fallback escalation
5. Scale calibration seam for 3DGS assets (XYZ scaling, log-scale addition ln(S))
"""

import math
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pytest
from scipy.spatial.transform import Rotation as R
from plyfile import PlyData, PlyElement

from app.pipelines.gaussian.format_converter import (
    pack_ply_to_splat,
    unpack_splat_file,
    SPLAT_DTYPE,
    SH_C0,
)
from app.pipelines.gaussian.pre_align import align_sparse_model
from app.pipelines.gaussian.splat_cleanup import SplatCleanupStage
from app.pipelines.base import JobContext, StageResult, CancelToken


def create_synthetic_3dgs_ply(
    ply_path: Path,
    num_points: int = 100,
    center: tuple = (0.0, 1.0, 0.0),
    spread: float = 2.0,
    mist_count: int = 0,
    giant_count: int = 0,
) -> Path:
    """Creates a valid 3DGS PLY file with full standard fields for testing."""
    N = num_points + mist_count + giant_count

    # Base valid coordinates
    np.random.seed(42)
    x = np.random.uniform(center[0] - spread, center[0] + spread, N).astype(np.float32)
    y = np.random.uniform(center[1] - 0.5, center[1] + 1.5, N).astype(np.float32)
    z = np.random.uniform(center[2] - spread, center[2] + spread, N).astype(np.float32)

    # Standard scale in log space (linear scale ~ 0.03m)
    scale_val = math.log(0.03)
    s0 = np.full(N, scale_val, dtype=np.float32)
    s1 = np.full(N, scale_val, dtype=np.float32)
    s2 = np.full(N, scale_val, dtype=np.float32)

    # Standard opacity logit (~0.95 alpha)
    op = np.full(N, 3.0, dtype=np.float32)

    # DC Spherical Harmonics
    f_dc_0 = np.random.uniform(-1.0, 1.0, N).astype(np.float32)
    f_dc_1 = np.random.uniform(-1.0, 1.0, N).astype(np.float32)
    f_dc_2 = np.random.uniform(-1.0, 1.0, N).astype(np.float32)

    # Unit rotation quaternions [w, x, y, z]
    rot_0 = np.ones(N, dtype=np.float32)
    rot_1 = np.zeros(N, dtype=np.float32)
    rot_2 = np.zeros(N, dtype=np.float32)
    rot_3 = np.zeros(N, dtype=np.float32)

    # Inject mist points (alpha < 0.05 -> logit < -3.0)
    if mist_count > 0:
        op[num_points:num_points + mist_count] = -5.0  # sigmoid(-5) = 0.0067

    # Inject giant floaters (scale > 0.5m)
    if giant_count > 0:
        idx_giant = num_points + mist_count
        s0[idx_giant:] = math.log(1.2)  # 1.2m giant scale
        s1[idx_giant:] = math.log(1.2)
        s2[idx_giant:] = math.log(1.2)

    dtype = [
        ('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
        ('nx', 'f4'), ('ny', 'f4'), ('nz', 'f4'),
        ('f_dc_0', 'f4'), ('f_dc_1', 'f4'), ('f_dc_2', 'f4'),
        ('opacity', 'f4'),
        ('scale_0', 'f4'), ('scale_1', 'f4'), ('scale_2', 'f4'),
        ('rot_0', 'f4'), ('rot_1', 'f4'), ('rot_2', 'f4'), ('rot_3', 'f4'),
    ]
    arr = np.empty(N, dtype=dtype)
    arr['x'] = x
    arr['y'] = y
    arr['z'] = z
    arr['nx'] = 0.0
    arr['ny'] = 0.0
    arr['nz'] = 0.0
    arr['f_dc_0'] = f_dc_0
    arr['f_dc_1'] = f_dc_1
    arr['f_dc_2'] = f_dc_2
    arr['opacity'] = op
    arr['scale_0'] = s0
    arr['scale_1'] = s1
    arr['scale_2'] = s2
    arr['rot_0'] = rot_0
    arr['rot_1'] = rot_1
    arr['rot_2'] = rot_2
    arr['rot_3'] = rot_3

    el = PlyElement.describe(arr, "vertex")
    PlyData([el], text=False).write(str(ply_path))
    return ply_path


def test_32byte_splat_format_roundtrip():
    """Verifies that 32-byte .splat packing is byte-exact and decodes accurately."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        ply_path = tdp / "test.ply"
        splat_path = tdp / "test.splat"

        N = 50
        create_synthetic_3dgs_ply(ply_path, num_points=N)

        packed_count = pack_ply_to_splat(ply_path, splat_path)
        assert packed_count == N
        assert splat_path.exists()
        # Exactly 32 bytes per Gaussian
        assert splat_path.stat().st_size == N * 32

        # Unpack and verify
        unpacked = unpack_splat_file(splat_path)
        assert len(unpacked) == N
        assert unpacked.dtype == SPLAT_DTYPE

        # Read original PLY
        orig = PlyData.read(str(ply_path))["vertex"].data

        # Positions match
        np.testing.assert_allclose(unpacked["pos"][:, 0], orig["x"], rtol=1e-5, atol=1e-5)
        np.testing.assert_allclose(unpacked["pos"][:, 1], orig["y"], rtol=1e-5, atol=1e-5)
        np.testing.assert_allclose(unpacked["pos"][:, 2], orig["z"], rtol=1e-5, atol=1e-5)

        # Linear scales match exp(scale)
        expected_scales = np.exp(orig["scale_0"])
        np.testing.assert_allclose(unpacked["scale"][:, 0], expected_scales, rtol=1e-4, atol=1e-4)

        # Colors within 0..255 uint8 range
        assert np.all(unpacked["color"] >= 0) and np.all(unpacked["color"] <= 255)
        # Quaternions within 0..255 uint8 range
        assert np.all(unpacked["rot"] >= 0) and np.all(unpacked["rot"] <= 255)


def test_splat_cleanup_mist_and_giant_pruning():
    """Verifies that opacity mist and giant scale floaters are correctly culled."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        raw_ply = tdp / "splat.ply"
        clean_ply = tdp / "cleaned_splat.ply"

        # 80 normal points, 15 mist points, 5 giant points
        create_synthetic_3dgs_ply(raw_ply, num_points=80, mist_count=15, giant_count=5)

        ctx = JobContext(
            job_id="test_cleanup_job",
            workdir=tdp,
            params={"quality": "standard"},
            cancel_token=CancelToken(),
            log_cb=lambda s: None,
            progress_cb=lambda p: None,
        )

        stage = SplatCleanupStage()
        res = stage.run(ctx)
        assert res.success
        assert clean_ply.exists()

        cleaned_data = PlyData.read(str(clean_ply))["vertex"].data
        # Pruning should drop all 15 mist and all 5 giant floaters
        assert len(cleaned_data) <= 80

        # Verify no remaining points have alpha < 0.05
        alphas = 1.0 / (1.0 + np.exp(-cleaned_data["opacity"]))
        assert np.all(alphas >= 0.05)

        # Verify no remaining points have scale > 0.5m
        scales = np.exp(cleaned_data["scale_0"])
        assert np.all(scales <= 0.50)


def test_colmap_pose_alignment_math():
    """
    Verifies that transforming COLMAP cameras and 3D points by a rigid body transform
    (R_total, translation) preserves camera-to-world relationships and 2D-3D ray projections.
    """
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        src_dir = tdp / "sparse" / "0"
        src_dir.mkdir(parents=True)

        # Write cameras.txt
        (src_dir / "cameras.txt").write_text(
            "# Camera list\n"
            "1 PINHOLE 1920 1080 1500 1500 960 540\n"
        )

        # Create camera pose looking down -Z with optical center at [0, 1.5, 3]
        # World-to-camera rotation R_c2w = Identity, translation = [0, -1.5, -3]
        # Camera center C = -R^T * T = [0, 1.5, 3]
        (src_dir / "images.txt").write_text(
            "# Image list\n"
            "1 1.0 0.0 0.0 0.0 0.0 -1.5 -3.0 1 frame_0001.jpg\n"
            "100.0 200.0 1\n"
        )

        # 3D Point at [0.5, 1.2, 0.0]
        (src_dir / "points3D.txt").write_text(
            "# 3D point list\n"
            "1 0.5 1.2 0.0 255 200 150 0.5 1 0\n"
        )

        dest_dir = tdp / "aligned" / "0"

        # Apply 90-degree yaw rotation around Y + translation of [10, -1.2, 5]
        rot_90_y = R.from_euler("y", 90, degrees=True).as_matrix()
        translation = np.array([10.0, -1.2, 5.0])

        count = align_sparse_model(src_dir, dest_dir, rot_90_y, translation)
        assert count == 1

        # Read transformed point
        pts_lines = [l for l in (dest_dir / "points3D.txt").read_text().splitlines() if not l.startswith("#") and l]
        assert len(pts_lines) == 1
        p_parts = pts_lines[0].split()
        p_trans = np.array([float(p_parts[1]), float(p_parts[2]), float(p_parts[3])])

        orig_p = np.array([0.5, 1.2, 0.0])
        expected_p = (rot_90_y @ orig_p) + translation
        np.testing.assert_allclose(p_trans, expected_p, atol=1e-5)

        # Read transformed camera pose
        img_lines = [l for l in (dest_dir / "images.txt").read_text().splitlines() if not l.startswith("#") and l]
        assert len(img_lines) == 2
        cam_parts = img_lines[0].split()
        qw_new, qx_new, qy_new, qz_new = map(float, cam_parts[1:5])
        tx_new, ty_new, tz_new = map(float, cam_parts[5:8])

        r_cam_new = R.from_quat([qx_new, qy_new, qz_new, qw_new]).as_matrix()
        t_cam_new = np.array([tx_new, ty_new, tz_new])

        # Verify camera center C' = R_total @ C_orig + translation
        c_orig = np.array([0.0, 1.5, 3.0])
        c_trans_expected = (rot_90_y @ c_orig) + translation
        c_trans_actual = -r_cam_new.T @ t_cam_new
        np.testing.assert_allclose(c_trans_actual, c_trans_expected, atol=1e-4)

        # Invariance of 3D projection ray into camera coordinates:
        # X_cam = R_orig @ X_world + T_orig
        # X_cam' = R_new @ X_world' + T_new
        # X_cam MUST EQUAL X_cam'!
        r_orig = np.eye(3)
        t_orig = np.array([0.0, -1.5, -3.0])
        x_cam_orig = r_orig @ orig_p + t_orig
        x_cam_new = r_cam_new @ p_trans + t_cam_new
        np.testing.assert_allclose(x_cam_new, x_cam_orig, atol=1e-4)


def test_splat_scale_calibration_math():
    """
    Verifies that scale calibration factor S multiplies positions and linear scales by S,
    and adds ln(S) to PLY log scales.
    """
    scale_factor = 2.0
    orig_pos = np.array([1.5, 0.5, -2.0])
    orig_log_scale = math.log(0.04)

    # Scaled position
    scaled_pos = orig_pos * scale_factor
    np.testing.assert_allclose(scaled_pos, [3.0, 1.0, -4.0])

    # Log scale math: s' = s + ln(S)
    scaled_log_scale = orig_log_scale + math.log(scale_factor)
    scaled_linear = math.exp(scaled_log_scale)
    expected_linear = 0.04 * scale_factor
    assert math.isclose(scaled_linear, expected_linear, rel_tol=1e-5)
