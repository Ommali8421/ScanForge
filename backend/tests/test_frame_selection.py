"""
Test Frame Selection and Extraction
Unit tests for adaptive frame sampling, sharpness scoring, duplicate filtering,
and fast-rotation/homography heuristics using programmatically generated test video.
"""

import json
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.pipelines.base import JobContext, CancelToken
from app.pipelines.common.frame_extraction import FrameExtractionStage


def create_synthetic_test_video(path: Path, num_frames: int = 50, fps: float = 10.0):
    """
    Generate synthetic test video with:
    - Frames 0..14: sharp high-contrast grid patterns (moving)
    - Frames 15..24: heavily blurred frames
    - Frames 25..34: completely static duplicate frames
    - Frames 35..49: rapidly rotating patterns (fast motion)
    """
    width, height = 320, 240
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))

    base_pattern = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(0, height, 20):
        for x in range(0, width, 20):
            if (x // 20 + y // 20) % 2 == 0:
                base_pattern[y:y+20, x:x+20] = (255, 255, 255)

    for i in range(num_frames):
        if i < 15:
            # Sharp moving frame
            dx = (i * 4) % width
            shifted = np.roll(base_pattern, dx, axis=1)
            frame = shifted
        elif i < 25:
            # Heavily blurred frame
            frame = cv2.GaussianBlur(base_pattern, (51, 51), 20.0)
        elif i < 35:
            # Static duplicate frame
            frame = base_pattern
        else:
            # Rapid rotation
            angle = (i - 35) * 25.0
            M = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
            frame = cv2.warpAffine(base_pattern, M, (width, height))

        out.write(frame)

    out.release()


def test_frame_extraction_adaptive_sampling(tmp_path: Path):
    """Verify that FrameExtractionStage accurately filters blur, dups, and detects fast rotation."""
    video_path = tmp_path / "normalized_input.mp4"
    create_synthetic_test_video(video_path, num_frames=60, fps=10.0)

    logs = []
    progress_updates = []

    ctx = JobContext(
        job_id="test-frame-extraction",
        workdir=tmp_path,
        params={},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: progress_updates.append((s, p, m)),
        log_cb=lambda l: logs.append(l)
    )

    stage = FrameExtractionStage()
    result = stage.run(ctx)

    assert result.success is True
    frames_dir = tmp_path / "frames"
    assert frames_dir.exists()
    extracted_frames = list(frames_dir.glob("*.jpg"))
    assert len(extracted_frames) > 0

    report_path = tmp_path / "frame_extraction_report.json"
    assert report_path.exists()

    with open(report_path, "r") as f:
        report = json.load(f)

    assert report["total_video_frames"] == 60
    assert report["candidate_frames_evaluated"] > 0
    assert report["frames_kept"] == len(extracted_frames)
    # Assert that blur or duplicate frames were dropped
    assert report["frames_dropped_blur"] + report["frames_dropped_duplicate"] + report["frames_dropped_fast_motion"] > 0
    assert report["mean_sharpness"] > 0


def test_frame_extraction_cancel(tmp_path: Path):
    """Verify that cancelling frame extraction stops execution cleanly."""
    video_path = tmp_path / "normalized_input.mp4"
    create_synthetic_test_video(video_path, num_frames=40, fps=10.0)

    cancel_token = CancelToken()
    cancel_token.cancel()

    ctx = JobContext(
        job_id="test-frame-cancel",
        workdir=tmp_path,
        params={},
        cancel_token=cancel_token,
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None
    )

    stage = FrameExtractionStage()
    with pytest.raises(RuntimeError, match="cancelled"):
        stage.run(ctx)
