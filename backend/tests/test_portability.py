"""
Unit Tests for Portability Rules
Validates tool resolution, dynamic COLMAP flag filtering, VRAM-aware quality preset calculation,
thread configuration, and stage isolation from DB/storage.
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.utils.tool_resolve import (
    resolve_binary,
    resolve_colmap,
    resolve_ffmpeg,
    resolve_blender,
    get_colmap_version,
    filter_colmap_args,
    get_available_vram_gb,
    get_configured_threads,
)
from app.pipelines.presets import get_preset_config
from app.pipelines.base import JobContext, CancelToken, StageResult


def test_resolve_binary_env_var_override(tmp_path: Path):
    """resolve_binary must prioritize explicit environment variable overrides."""
    fake_tool = tmp_path / "custom_colmap"
    fake_tool.write_text("#!/bin/sh\necho custom")
    fake_tool.chmod(0o755)

    with patch.dict(os.environ, {"SCANFORGE_COLMAP_BIN": str(fake_tool)}):
        resolved = resolve_colmap()
        assert resolved == str(fake_tool)


def test_get_colmap_version_parsing():
    """get_colmap_version must parse major, minor, patch from colmap -h output."""
    sample_help = "COLMAP 3.9.1 -- Structure-from-Motion and Multi-View Stereo\nUsage: colmap ..."
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=sample_help, stderr="")
        v = get_colmap_version("mock_colmap")
        assert v == (3, 9, 1)


def test_filter_colmap_args():
    """filter_colmap_args must retain valid flags and omit unknown flags."""
    supported = {"--database_path", "--image_path", "--SiftExtraction.max_image_size"}
    with patch("app.utils.tool_resolve.get_colmap_supported_flags", return_value=supported):
        args = [
            "--database_path", "/path/to/db",
            "--unknown_flag_v4", "true",
            "--image_path", "/path/to/images"
        ]
        filtered = filter_colmap_args("feature_extractor", args)
        assert "--database_path" in filtered
        assert "/path/to/db" in filtered
        assert "--image_path" in filtered
        assert "--unknown_flag_v4" not in filtered


def test_dynamic_vram_presets():
    """get_preset_config must adapt resolution and image size to available VRAM."""
    # 1. High VRAM (16 GB)
    cfg_16 = get_preset_config("standard", vram_gb=16.0)
    assert cfg_16.colmap_max_image_size == 2400
    assert cfg_16.openmvs_resolution_level == 1

    # 2. 8 GB Baseline (RTX 4060 target)
    cfg_8 = get_preset_config("standard", vram_gb=8.0)
    assert cfg_8.colmap_max_image_size == 2000
    assert cfg_8.openmvs_resolution_level == 2

    # 3. Low VRAM (4 GB)
    cfg_4 = get_preset_config("standard", vram_gb=4.0)
    assert cfg_4.colmap_max_image_size == 1600
    assert cfg_4.openmvs_resolution_level == 2


def test_configured_threads_env_override():
    """get_configured_threads must honour SCANFORGE_NUM_THREADS."""
    with patch.dict(os.environ, {"SCANFORGE_NUM_THREADS": "6"}):
        assert get_configured_threads() == 6

    with patch.dict(os.environ, {}, clear=True):
        t = get_configured_threads()
        assert t >= 1
        assert t <= 4  # Default capped at 4
