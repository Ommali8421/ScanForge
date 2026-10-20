"""
Test SfM Failure Handling and Registration Thresholds
Validates that COLMAP SfM stage cleanly fails when registration ratio is <60%,
properly handles missing input frames, and provides informative diagnostics.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.pipelines.base import JobContext, CancelToken
from app.pipelines.common.sfm_colmap import ColmapSfMStage


def test_sfm_missing_frames_dir(tmp_path: Path):
    """SfM stage should fail immediately if frames directory does not exist."""
    ctx = JobContext(
        job_id="test-sfm-missing",
        workdir=tmp_path,
        params={},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None
    )
    stage = ColmapSfMStage()
    with pytest.raises(FileNotFoundError):
        stage.run(ctx)


def test_sfm_empty_frames_dir(tmp_path: Path):
    """SfM stage should fail if frames directory exists but has no images."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()

    ctx = JobContext(
        job_id="test-sfm-empty",
        workdir=tmp_path,
        params={},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None
    )
    stage = ColmapSfMStage()
    with pytest.raises(RuntimeError, match="No input frames found"):
        stage.run(ctx)


def test_sfm_registration_below_threshold(tmp_path: Path):
    """SfM stage should reject models that register <60% of input frames."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    # Create 10 dummy image files
    for i in range(10):
        (frames_dir / f"frame_{i:04d}.jpg").write_text("dummy")

    ctx = JobContext(
        job_id="test-sfm-threshold",
        workdir=tmp_path,
        params={"options": {"matcher": "exhaustive"}},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda l: None
    )

    stage = ColmapSfMStage()

    # Mock ToolRunner.run to succeed for extraction/matching/mapper
    with patch("app.pipelines.common.sfm_colmap.ToolRunner.run") as mock_run:
        # Mock _find_best_model to return a model with only 4/10 registered frames (40% < 60%)
        dummy_model_dir = tmp_path / "sparse" / "0"
        dummy_model_dir.mkdir(parents=True)
        with patch.object(stage, "_find_best_model", return_value=(dummy_model_dir, 4)):
            with pytest.raises(RuntimeError, match="Registration check failed at stage 'sfm'"):
                stage.run(ctx)
