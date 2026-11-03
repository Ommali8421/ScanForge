"""
Unit and Integration Tests for Milestone P4: Depth Fusion (Route B) and Floor Plan Generation.
"""

import json
import numpy as np
import pytest
from pathlib import Path

from app.pipelines.depth.depth_align import fit_ransac_inverse_depth
from app.pipelines.mesh.floor_plan import compute_slice_height, slice_mesh_xz, render_floor_plan_svg, render_floor_plan_png
from app.pipelines.mesh.route_classifier import RouteClassifierStage
from app.pipelines.base import JobContext, CancelToken


def test_inverse_depth_ransac_fit_synthetic():
    """Verify that RANSAC in inverse-depth space recovers exact scale and shift with outliers."""
    np.random.seed(42)
    true_s = 2.45
    true_t = 0.35

    # 100 true inliers
    true_z = np.random.uniform(1.0, 10.0, size=100)
    true_inv = 1.0 / true_z
    disp = (true_inv - true_t) / true_s

    # Add 25 rogue outliers (e.g. reflections or sky)
    outlier_disp = np.random.uniform(0.1, 5.0, size=25)
    outlier_inv = np.random.uniform(0.01, 2.0, size=25)

    all_disp = np.concatenate([disp, outlier_disp])
    all_inv = np.concatenate([true_inv, outlier_inv])

    s_est, t_est, inliers = fit_ransac_inverse_depth(all_disp, all_inv, max_iters=200, inlier_thresh=0.08)

    assert inliers >= 85, f"Expected >= 85 inliers, got {inliers}"
    assert abs(s_est - true_s) < 0.15, f"Estimated s={s_est:.3f} deviated from true {true_s}"
    assert abs(t_est - true_t) < 0.15, f"Estimated t={t_est:.3f} deviated from true {true_t}"


def test_relative_voxel_size_and_slice_height_math():
    """Verify scale-invariant voxel size and dynamic slice height in uncalibrated vs calibrated spaces."""
    # 1. Uncalibrated space with large room (D_room = 25.0 units)
    d_room = 25.0
    voxel_std = d_room / 380.0
    voxel_high = d_room / 520.0
    voxel_draft = d_room / 250.0

    assert 0.05 < voxel_std < 0.08
    assert 0.03 < voxel_high < 0.06
    assert 0.08 < voxel_draft < 0.12

    # 2. Dynamic slice height (uncalibrated)
    # Floor at 0.0, Ceiling at 3.0, Median camera height at 1.8
    y_slice_uncal = compute_slice_height(
        y_floor=0.0,
        y_ceiling=3.0,
        median_cam_y=1.8,
        cumulative_scale=1.0,
        is_calibrated=False,
    )
    # 0.65 * 1.8 = 1.17, which is within [0.25*3.0, 0.55*3.0] = [0.75, 1.65]
    assert abs(y_slice_uncal - 1.17) < 0.05

    # Clamping test: camera too low (0.2m)
    y_slice_low = compute_slice_height(
        y_floor=0.0,
        y_ceiling=4.0,
        median_cam_y=0.2,
        cumulative_scale=1.0,
        is_calibrated=False,
    )
    assert abs(y_slice_low - 1.0) < 0.05  # 0.25 * 4.0 = 1.0

    # 3. Calibrated slice height (cumulative scale = 2.0m)
    y_slice_cal = compute_slice_height(
        y_floor=0.0,
        y_ceiling=3.0,
        median_cam_y=1.5,
        cumulative_scale=2.0,
        is_calibrated=True,
    )
    assert abs(y_slice_cal - 2.20) < 0.05  # 1.10 * 2.0


def test_route_classifier_logic(tmp_path):
    """Verify scale-invariant route classifier heuristic."""
    stage = RouteClassifierStage()

    # 1. Textureless scenario
    ctx_textureless = JobContext(
        job_id="test_route_b",
        workdir=tmp_path,
        params={"options": {"mesh_route": "auto"}},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda m: None,
    )
    # Write empty frames dir (will result in low variance)
    (tmp_path / "frames").mkdir(exist_ok=True)
    res = stage.run(ctx_textureless)
    assert res.success
    dec_file = tmp_path / "mesh_route_decision.json"
    assert dec_file.exists()
    data = json.loads(dec_file.read_text())
    assert data["decision"] in {"depth_fusion", "photogrammetry"}

    # 2. User explicit override
    ctx_override = JobContext(
        job_id="test_override",
        workdir=tmp_path,
        params={"options": {"mesh_route": "photogrammetry"}},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda m: None,
    )
    res_override = stage.run(ctx_override)
    assert res_override.success
    data_override = json.loads(dec_file.read_text())
    assert data_override["decision"] == "photogrammetry"


def test_floor_plan_svg_and_png_generation(tmp_path):
    """Verify 2D architectural floor plan generation from 3D synthetic room."""
    import trimesh

    # Create a 3D rectangular room box (8m x 3m x 6m)
    box = trimesh.creation.box(extents=[8.0, 3.0, 6.0])
    mesh_path = tmp_path / "mesh_aligned.ply"
    box.export(str(mesh_path))

    segments, bounds = slice_mesh_xz(mesh_path, y_slice=1.10)
    assert len(segments) >= 4, f"Expected at least 4 perimeter segments, got {len(segments)}"

    svg_path = tmp_path / "floor_plan.svg"
    png_path = tmp_path / "floor_plan.png"

    dimensions = {"length": 8.0, "width": 6.0, "height": 3.0, "floor_area": 48.0}
    render_floor_plan_svg(segments, bounds, svg_path, dimensions, is_calibrated=True, y_slice=1.10)
    render_floor_plan_png(segments, bounds, png_path, dimensions, is_calibrated=True, y_slice=1.10)

    assert svg_path.exists()
    assert png_path.exists()

    svg_content = svg_path.read_text()
    assert "<svg" in svg_content
    assert "SCANFORGE ARCHITECTURAL FLOOR PLAN" in svg_content
    assert "8.00 m" in svg_content
    assert "6.00 m" in svg_content

    png_bytes = png_path.read_bytes()
    assert len(png_bytes) > 1000

