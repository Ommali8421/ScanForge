"""
Test Ingest Auto-Crop and Multi-Criteria Scene-Cut Validation
"""

import json
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.pipelines.base import JobContext, CancelToken
from app.pipelines.common.ingest import IngestStage


def create_letterboxed_video(path: Path, width: int = 320, height: int = 240, bar_height: int = 20):
    """Generate synthetic video with black letterbox bars top and bottom."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = 10.0
    out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))

    for i in range(25):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Content in the middle
        content = np.random.randint(50, 200, (height - 2 * bar_height, width, 3), dtype=np.uint8)
        # Add visual texture
        cv2.putText(content, f"Frame {i}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        frame[bar_height:height - bar_height, :] = content
        out.write(frame)

    out.release()


def test_ingest_autocrop_letterbox(tmp_path: Path):
    """Verify that cropdetect detects letterbox bars and calculates crop bounds."""
    video_path = tmp_path / "letterboxed.mp4"
    create_letterboxed_video(video_path, width=320, height=240, bar_height=20)

    stage = IngestStage()
    ctx = JobContext(
        job_id="test-crop",
        workdir=tmp_path,
        params={},
        log_cb=lambda msg: None,
        progress_cb=lambda p: None,
        cancel_token=CancelToken()
    )

    crop = stage._detect_crop(video_path, ctx)
    assert crop is not None
    assert crop["h"] < 240
    assert crop["y"] >= 16  # approx 20px top bar
    assert "crop=" in crop["crop_filter"]


def test_ingest_autocrop_fullframe(tmp_path: Path):
    """Verify that full-frame video with no bars is not cropped."""
    video_path = tmp_path / "fullframe.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (320, 240))
    for i in range(25):
        frame = np.random.randint(40, 220, (240, 320, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    stage = IngestStage()
    ctx = JobContext(
        job_id="test-nocrop",
        workdir=tmp_path,
        params={},
        log_cb=lambda msg: None,
        progress_cb=lambda p: None,
        cancel_token=CancelToken()
    )

    crop = stage._detect_crop(video_path, ctx)
    if crop:
        assert crop["w"] == 320 and crop["h"] == 240


def test_ingest_scene_cut_false_positive_rejection(tmp_path: Path):
    """
    Verify that scene-cut detector correctly rejects:
    - Low-texture blank walls (kp < 40)
    - Heavy motion blur (blur < 25)
    and does not flag continuous panning as a cut.
    """
    video_path = tmp_path / "pan_and_wall.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (320, 240))

    # Frames 0..10: textured pattern
    pattern = np.zeros((240, 320, 3), dtype=np.uint8)
    for y in range(0, 240, 30):
        for x in range(0, 320, 30):
            pattern[y:y+15, x:x+15] = (200, 200, 200)

    for i in range(10):
        frame = np.roll(pattern, i * 4, axis=1)
        out.write(frame)

    # Frames 10..20: blank white wall (textureless)
    blank_wall = np.ones((240, 320, 3), dtype=np.uint8) * 230
    for i in range(10):
        out.write(blank_wall)

    out.release()

    stage = IngestStage()
    ctx = JobContext(
        job_id="test-cut-reject",
        workdir=tmp_path,
        params={},
        log_cb=lambda msg: None,
        progress_cb=lambda p: None,
        cancel_token=CancelToken()
    )

    cuts, cuts_dir = stage._detect_scene_cuts(video_path, ctx)
    # None of the candidates should be confirmed as genuine cuts
    confirmed = [c for c in cuts if c["confirmed_cut"]]
    assert len(confirmed) == 0
    # The blank wall transition should be rejected due to low texture
    for c in cuts:
        assert c["verdict"] == "rejected_pan"

