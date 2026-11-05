"""
Unit test for 4K frame extraction capping to guarantee 8 GB VRAM safety.
"""
import numpy as np
from app.pipelines.common.frame_extraction import _cap_frame_resolution

def test_4k_frame_capping():
    # 4K frame (3840 x 2160 landscape)
    frame_4k = np.zeros((2160, 3840, 3), dtype=np.uint8)
    capped = _cap_frame_resolution(frame_4k, max_edge_limit=1920)
    assert capped.shape == (1080, 1920, 3), f"Expected (1080, 1920, 3), got {capped.shape}"

    # 4K portrait frame (2160 x 3840)
    frame_4k_port = np.zeros((3840, 2160, 3), dtype=np.uint8)
    capped_port = _cap_frame_resolution(frame_4k_port, max_edge_limit=1920)
    assert capped_port.shape == (1920, 1080, 3), f"Expected (1920, 1080, 3), got {capped_port.shape}"

    # 1080p frame (1920 x 1080) - should NOT be altered
    frame_1080 = np.zeros((1080, 1920, 3), dtype=np.uint8)
    capped_1080 = _cap_frame_resolution(frame_1080, max_edge_limit=1920)
    assert capped_1080.shape == (1080, 1920, 3)

    # Sub-1080p frame (850 x 478) - should NOT be upscaled
    frame_sub = np.zeros((850, 478, 3), dtype=np.uint8)
    capped_sub = _cap_frame_resolution(frame_sub, max_edge_limit=1920)
    assert capped_sub.shape == (850, 478, 3)

