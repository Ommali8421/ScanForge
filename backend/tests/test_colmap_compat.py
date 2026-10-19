"""
Unit Tests for COLMAP Multi-Version Compatibility (3.9.1 vs 3.13.0)
Validates option renaming maps derived directly from real help output fixtures,
ensuring thread limit, GPU, and max-image-size flags are never dropped,
verifying hang protection, loop detection fallback, and raising on unmappable critical flags.
"""

from pathlib import Path
from unittest.mock import patch
import pytest

from app.utils.colmap_compat import (
    ColmapFlagMappingError,
    load_colmap_help_fixture,
    build_feature_extractor_args,
    build_sequential_matcher_args,
    build_exhaustive_matcher_args,
    build_vocab_tree_matcher_args,
    build_mapper_args,
    map_colmap_option,
    configure_loop_detection,
    verify_rename_map_against_fixtures,
)
from app.utils.tool_resolve import filter_colmap_args


def test_rename_map_verified_from_real_fixtures():
    """All mapped flags must exist in the real help fixtures (3.9.1 and 3.13.0)."""
    results = verify_rename_map_against_fixtures()
    assert "3.9.1" in results
    assert "3.13" in results

    # Ensure all key subcommands were verified
    expected_subcmds = {"feature_extractor", "sequential_matcher", "exhaustive_matcher", "vocab_tree_matcher", "mapper"}
    assert set(results["3.9.1"].keys()) == expected_subcmds
    assert set(results["3.13"].keys()) == expected_subcmds


def test_feature_extractor_flags_3_9_vs_3_13():
    """
    Feature extraction:
    - 3.9.x: --SiftExtraction.use_gpu, --SiftExtraction.num_threads, --SiftExtraction.max_image_size
    - 3.13+: --FeatureExtraction.use_gpu, --FeatureExtraction.num_threads, --SiftExtraction.max_image_size
    Nothing dropped.
    """
    help_391 = load_colmap_help_fixture("3.9.1")["feature_extractor"]
    help_313 = load_colmap_help_fixture("3.13")["feature_extractor"]

    # 1. Test COLMAP 3.9.1
    args_391 = build_feature_extractor_args(
        version=(3, 9, 1),
        database_path="/tmp/colmap.db",
        image_path="/tmp/frames",
        camera_model="SIMPLE_RADIAL",
        single_camera=True,
        max_image_size=2000,
        use_gpu=True,
        threads=4,
        supported_flags=help_391,
    )
    assert "--SiftExtraction.use_gpu" in args_391
    assert args_391[args_391.index("--SiftExtraction.use_gpu") + 1] == "1"
    assert "--SiftExtraction.num_threads" in args_391
    assert args_391[args_391.index("--SiftExtraction.num_threads") + 1] == "4"
    assert "--SiftExtraction.max_image_size" in args_391
    assert args_391[args_391.index("--SiftExtraction.max_image_size") + 1] == "2000"
    assert "--FeatureExtraction.use_gpu" not in args_391

    # 2. Test COLMAP 3.13.0
    args_313 = build_feature_extractor_args(
        version=(3, 13, 0),
        database_path="/tmp/colmap.db",
        image_path="/tmp/frames",
        camera_model="SIMPLE_RADIAL",
        single_camera=True,
        max_image_size=2000,
        use_gpu=True,
        threads=4,
        supported_flags=help_313,
    )
    assert "--FeatureExtraction.use_gpu" in args_313
    assert args_313[args_313.index("--FeatureExtraction.use_gpu") + 1] == "1"
    assert "--FeatureExtraction.num_threads" in args_313
    assert args_313[args_313.index("--FeatureExtraction.num_threads") + 1] == "4"
    assert "--SiftExtraction.max_image_size" in args_313
    assert args_313[args_313.index("--SiftExtraction.max_image_size") + 1] == "2000"
    assert "--SiftExtraction.use_gpu" not in args_313


def test_sequential_matcher_both_threads_on_3_13():
    """
    Sequential matcher:
    - 3.9.x: --SiftMatching.num_threads, --SiftMatching.use_gpu
    - 3.13+: sets BOTH --FeatureMatching.num_threads AND --SequentialMatching.num_threads,
             plus --FeatureMatching.use_gpu
    """
    help_391 = load_colmap_help_fixture("3.9.1")["sequential_matcher"]
    help_313 = load_colmap_help_fixture("3.13")["sequential_matcher"]

    # 3.9.1
    args_391 = build_sequential_matcher_args(
        version=(3, 9, 1),
        database_path="/tmp/colmap.db",
        use_gpu=True,
        threads=4,
        supported_flags=help_391,
    )
    assert "--SiftMatching.use_gpu" in args_391
    assert "--SiftMatching.num_threads" in args_391
    assert "--SequentialMatching.num_threads" not in args_391

    # 3.13.0
    args_313 = build_sequential_matcher_args(
        version=(3, 13, 0),
        database_path="/tmp/colmap.db",
        use_gpu=True,
        threads=4,
        supported_flags=help_313,
    )
    assert "--FeatureMatching.use_gpu" in args_313
    assert "--FeatureMatching.num_threads" in args_313
    assert args_313[args_313.index("--FeatureMatching.num_threads") + 1] == "4"
    assert "--SequentialMatching.num_threads" in args_313
    assert args_313[args_313.index("--SequentialMatching.num_threads") + 1] == "4"


def test_exhaustive_and_vocab_tree_matcher_threads():
    """
    Exhaustive & VocabTree matchers:
    - VocabTree on 3.13 sets BOTH --FeatureMatching.num_threads and --VocabTreeMatching.num_threads.
    - Exhaustive on 3.13 sets --FeatureMatching.num_threads.
    """
    help_313 = load_colmap_help_fixture("3.13")

    # VocabTree 3.13
    v_args = build_vocab_tree_matcher_args(
        version=(3, 13, 0),
        database_path="/tmp/colmap.db",
        vocab_tree_path="/tmp/vocab.bin",
        use_gpu=True,
        threads=6,
        supported_flags=help_313["vocab_tree_matcher"],
    )
    assert "--FeatureMatching.use_gpu" in v_args
    assert "--FeatureMatching.num_threads" in v_args
    assert v_args[v_args.index("--FeatureMatching.num_threads") + 1] == "6"
    assert "--VocabTreeMatching.num_threads" in v_args
    assert v_args[v_args.index("--VocabTreeMatching.num_threads") + 1] == "6"

    # Exhaustive 3.13
    e_args = build_exhaustive_matcher_args(
        version=(3, 13, 0),
        database_path="/tmp/colmap.db",
        use_gpu=False,
        threads=2,
        supported_flags=help_313["exhaustive_matcher"],
    )
    assert "--FeatureMatching.use_gpu" in e_args
    assert e_args[e_args.index("--FeatureMatching.use_gpu") + 1] == "0"
    assert "--FeatureMatching.num_threads" in e_args
    assert e_args[e_args.index("--FeatureMatching.num_threads") + 1] == "2"


def test_unmappable_critical_flag_raises():
    """Unmappable or dropped critical flag must raise ColmapFlagMappingError."""
    # 1. Direct map_colmap_option with unsupported critical option
    with pytest.raises(ColmapFlagMappingError):
        map_colmap_option("mapper", "non_existent_critical_feature", "val", (3, 9, 1), is_critical=True)

    # 2. build_feature_extractor_args when critical flag is missing from supported_flags
    incomplete_flags = {"--database_path", "--image_path", "--ImageReader.camera_model", "--ImageReader.single_camera"}
    with pytest.raises(ColmapFlagMappingError):
        build_feature_extractor_args(
            version=(3, 13, 0),
            database_path="db",
            image_path="imgs",
            supported_flags=incomplete_flags,  # Missing FeatureExtraction.num_threads / use_gpu
        )

    # 3. filter_colmap_args with critical_flags parameter
    with patch("app.utils.tool_resolve.get_colmap_supported_flags", return_value={"--database_path"}):
        with pytest.raises(ColmapFlagMappingError):
            filter_colmap_args(
                "feature_extractor",
                ["--database_path", "db", "--SiftExtraction.max_image_size", "2000"],
                critical_flags={"--SiftExtraction.max_image_size"}
            )


def test_mapper_hang_protection_per_version():
    """
    Mapper hang protection:
    - 3.13: uses --Mapper.max_runtime_seconds <timeout> and timeout+30 ToolRunner buffer.
    - 3.9.x: ToolRunner timeout enforces hang protection without low Ceres iteration caps.
    """
    help_391 = load_colmap_help_fixture("3.9.1")["mapper"]
    help_313 = load_colmap_help_fixture("3.13")["mapper"]

    # 3.9.1
    args_391, timeout_391 = build_mapper_args(
        version=(3, 9, 1),
        database_path="db",
        image_path="imgs",
        output_path="out",
        threads=4,
        timeout_seconds=1200,
        supported_flags=help_391,
    )
    assert "--Mapper.num_threads" in args_391
    assert "--Mapper.max_runtime_seconds" not in args_391
    assert timeout_391 == 1200
    # No low Ceres caps injected
    assert "--Mapper.ba_global_max_num_iterations" not in args_391

    # 3.13.0
    args_313, timeout_313 = build_mapper_args(
        version=(3, 13, 0),
        database_path="db",
        image_path="imgs",
        output_path="out",
        threads=4,
        timeout_seconds=1200,
        supported_flags=help_313,
    )
    assert "--Mapper.num_threads" in args_313
    assert "--Mapper.max_runtime_seconds" in args_313
    assert args_313[args_313.index("--Mapper.max_runtime_seconds") + 1] == "1200"
    assert timeout_313 == 1230  # Margin for clean shutdown
    assert "--Mapper.ba_global_max_num_iterations" not in args_313


def test_loop_detection_behavior(tmp_path: Path):
    """
    Loop detection:
    - 3.13: auto-downloads FAISS vocab tree by default (needs internet).
    - 3.9.1: needs local vocab tree file; logs warning and falls back if missing.
    - Local file works on both versions.
    """
    # 1. 3.13 without local file: auto-download strategy
    enabled, vocab_path, msg = configure_loop_detection((3, 13, 0))
    assert enabled is True
    assert vocab_path is None
    assert "auto-download FAISS" in msg

    # 2. 3.9.1 without local file: warning and disable loop detection
    logs = []
    enabled_39, vocab_path_39, msg_39 = configure_loop_detection((3, 9, 1), log_cb=logs.append)
    assert enabled_39 is False
    assert vocab_path_39 is None
    assert "Warning" in msg_39
    assert len(logs) == 1

    # 3. Local file present: used on both
    fake_tree = tmp_path / "vocab_tree.bin"
    fake_tree.write_text("fake binary")

    enabled_local, path_local, msg_local = configure_loop_detection((3, 9, 1), custom_vocab_path=str(fake_tree))
    assert enabled_local is True
    assert path_local == str(fake_tree)
    assert "local vocabulary tree" in msg_local


def test_mapper_ba_use_gpu_flag():
    """Mapper ba_use_gpu is optional and disabled by default on 3.13."""
    help_313 = load_colmap_help_fixture("3.13")["mapper"]

    # Default: disabled
    args_default, _ = build_mapper_args((3, 13, 0), "db", "imgs", "out", ba_use_gpu=False, supported_flags=help_313)
    assert "--Mapper.ba_use_gpu" not in args_default

    # Explicitly enabled
    args_enabled, _ = build_mapper_args((3, 13, 0), "db", "imgs", "out", ba_use_gpu=True, supported_flags=help_313)
    assert "--Mapper.ba_use_gpu" in args_enabled
    assert args_enabled[args_enabled.index("--Mapper.ba_use_gpu") + 1] == "1"
