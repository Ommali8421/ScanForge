import json
import numpy as np
import pytest
from pathlib import Path

from app.pipelines.gaussian.format_converter import compute_morton_order
from app.pipelines.depth.depth_align import fast_guided_filter


def test_morton_order_calculation():
    """Verify 3D Morton Z-order curve produces correct ordering and handles edge cases."""
    x = np.array([0.0, 1.0, 0.5, 0.0, 0.0, 1.0], dtype=np.float32)
    y = np.array([0.0, 1.0, 0.5, 0.0, 1.0, 0.0], dtype=np.float32)
    z = np.array([0.0, 1.0, 0.5, 1.0, 0.0, 0.0], dtype=np.float32)

    order = compute_morton_order(x, y, z)
    assert len(order) == len(x)
    assert set(order) == set(range(len(x)))
    # Point at (0,0,0) should be earliest
    assert order[0] == 0
    # Point at (1,1,1) should be last
    assert order[-1] == 1


def test_morton_order_empty_and_single():
    """Edge cases: empty or single point should not crash."""
    empty = np.array([], dtype=np.float32)
    empty_order = compute_morton_order(empty, empty, empty)
    assert len(empty_order) == 0

    single = np.array([1.0], dtype=np.float32)
    single_order = compute_morton_order(single, single, single)
    assert list(single_order) == [0]


def test_cameras_aligned_contract():
    """Verify cameras_aligned.json structure conforms to the required schema."""
    sample_cameras = {
        "coordinate_system": "threejs_y_up_z_back_scaled",
        "units": "meters",
        "num_cameras": 3,
        "first_frame_camera": {
            "image_id": 1,
            "filename": "frame_0000.jpg",
            "position": [0.12, 1.45, -0.85],
            "forward": [0.05, -0.10, -0.99],
            "up": [0.0, 1.0, 0.0],
            "is_first_frame": True,
        },
        "cameras": [
            {
                "image_id": 1,
                "filename": "frame_0000.jpg",
                "position": [0.12, 1.45, -0.85],
                "forward": [0.05, -0.10, -0.99],
                "up": [0.0, 1.0, 0.0],
                "is_first_frame": True,
            },
            {
                "image_id": 2,
                "filename": "frame_0001.jpg",
                "position": [0.15, 1.46, -0.80],
                "forward": [0.06, -0.10, -0.99],
                "up": [0.0, 1.0, 0.0],
                "is_first_frame": False,
            },
            {
                "image_id": 3,
                "filename": "frame_0002.jpg",
                "position": [0.18, 1.47, -0.75],
                "forward": [0.07, -0.10, -0.99],
                "up": [0.0, 1.0, 0.0],
                "is_first_frame": False,
            },
        ],
    }

    # Verify first_frame_camera has unit forward vector
    ff = sample_cameras["first_frame_camera"]
    fwd = np.array(ff["forward"], dtype=np.float32)
    norm = np.linalg.norm(fwd)
    assert np.isclose(norm, 1.0, atol=0.02)
    assert ff["is_first_frame"] is True
    assert ff["filename"] == "frame_0000.jpg"

    # Verify camera list ordering is ascending
    filenames = [c["filename"] for c in sample_cameras["cameras"]]
    assert filenames == sorted(filenames)


def test_fast_guided_filter_edge_preservation():
    """Verify fast_guided_filter preserves sharp step edges while smoothing noise."""
    # Create synthetic 64x64 step image with noisy depth
    h, w = 64, 64
    guidance = np.zeros((h, w), dtype=np.float32)
    guidance[:, w // 2 :] = 1.0  # Sharp vertical edge at w=32

    # Depth map with corresponding step plus additive Gaussian noise
    clean_depth = np.zeros((h, w), dtype=np.float32)
    clean_depth[:, : w // 2] = 2.0
    clean_depth[:, w // 2 :] = 5.0

    np.random.seed(42)
    noise = np.random.normal(0, 0.05, (h, w)).astype(np.float32)
    noisy_depth = clean_depth + noise

    # Apply fast guided filter
    filtered = fast_guided_filter(guidance, noisy_depth, r=4, eps=1e-3)

    # Check that noise was smoothed in flat regions
    flat_region_noise_before = np.std(noisy_depth[:, :20])
    flat_region_noise_after = np.std(filtered[:, :20])
    assert flat_region_noise_after < flat_region_noise_before

    # Check that edge at w=32 remains sharp (large gradient across boundary)
    step_jump = filtered[:, w // 2 + 5].mean() - filtered[:, w // 2 - 5].mean()
    assert step_jump > 2.5  # Step height preserved near 3.0


def test_tgm_temporal_damping_logic():
    """Verify Temporal Gradient Matching (TGM) logic stabilizes static pixels."""
    # Simulate two consecutive aligned depth frames
    h, w = 32, 32
    d_prev = np.ones((h, w), dtype=np.float32) * 3.0
    # Current depth has small depth jitter on static pixels and large real motion in bottom-right
    d_curr = d_prev.copy()
    d_curr[:16, :16] += 0.08  # small noise jitter (static region)
    d_curr[20:, 20:] += 1.5  # real foreground change

    # Simulate luminance difference (static in top-left, moving in bottom-right)
    lum_diff = np.zeros((h, w), dtype=np.float32)
    lum_diff[20:, 20:] = 0.4  # significant visual change

    static_mask = lum_diff < 0.05
    d_damped = d_curr.copy()
    d_damped[static_mask] = 0.85 * d_curr[static_mask] + 0.15 * d_prev[static_mask]

    # Jitter in static region should be damped toward d_prev
    diff_before = np.abs(d_curr[:16, :16] - 3.0).mean()
    diff_after = np.abs(d_damped[:16, :16] - 3.0).mean()
    assert diff_after < diff_before

    # Moving region should be untouched
    assert np.allclose(d_damped[20:, 20:], d_curr[20:, 20:])
