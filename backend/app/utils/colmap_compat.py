"""
ScanForge COLMAP Version Compatibility & Flag Mapping Module
Handles differences between COLMAP 3.9.x and COLMAP 3.13.x+ based on verified
help output fixtures (colmap_help_3.9.1.txt and colmap_help_3.13.txt).

Key differences verified from fixtures:
1. Feature Extraction:
   - 3.9.x: --SiftExtraction.use_gpu, --SiftExtraction.num_threads
   - 3.13+: --FeatureExtraction.use_gpu, --FeatureExtraction.num_threads
   - Both:  --SiftExtraction.max_image_size (unchanged)

2. Feature Matching:
   - 3.9.x: --SiftMatching.use_gpu, --SiftMatching.num_threads,
            --SiftMatching.guided_matching, --SiftMatching.max_num_matches
   - 3.13+: --FeatureMatching.use_gpu, --FeatureMatching.num_threads,
            --FeatureMatching.guided_matching, --FeatureMatching.max_num_matches
   - 3.13+ Matcher-specific threads:
     * SequentialMatching: sets BOTH --FeatureMatching.num_threads AND --SequentialMatching.num_threads
     * VocabTreeMatching: sets BOTH --FeatureMatching.num_threads AND --VocabTreeMatching.num_threads

3. Mapper:
   - Both:  --Mapper.num_threads (unchanged)
   - 3.13+: --Mapper.max_runtime_seconds (hang protection)
   - 3.13+: --Mapper.ba_use_gpu (optional, disabled by default)

4. Loop Detection:
   - 3.13+: auto-downloads FAISS vocabulary tree by default (needs internet)
   - 3.9.x: requires a local vocabulary tree file; falls back to no loop detection if absent.
"""

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.utils.logging import logger


class ColmapFlagMappingError(ValueError):
    """Raised when a critical flag cannot be mapped or supported for a target COLMAP version."""
    pass


# Default fixture directory relative to repo root
FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "colmap_help"


def parse_colmap_help_text(help_text: str) -> Dict[str, Set[str]]:
    """
    Parse a composite colmap help text (like colmap_help_*.txt) into a dictionary
    mapping subcommand -> set of supported CLI flags (--flag_name).
    """
    sections = re.split(r"=====\s*colmap\s+([a-zA-Z0-9_\-]+)\s*(?:-h)?\s*=====", help_text)
    subcommand_flags: Dict[str, Set[str]] = {}

    for i in range(1, len(sections), 2):
        subcmd = sections[i].strip()
        content = sections[i + 1]
        matches = set(re.findall(r"(--[a-zA-Z0-9_\.]+)", content))
        subcommand_flags[subcmd] = matches

    return subcommand_flags


def load_colmap_help_fixture(version_str: str) -> Dict[str, Set[str]]:
    """
    Load and parse a saved fixture file (e.g. '3.9.1' or '3.13').
    """
    fixture_filename = f"colmap_help_{version_str}.txt"
    fixture_path = FIXTURES_DIR / fixture_filename
    if not fixture_path.exists():
        raise FileNotFoundError(f"COLMAP help fixture not found at {fixture_path}")

    return parse_colmap_help_text(fixture_path.read_text(encoding="utf-8"))


# =============================================================================
# Verified Rename Map
# Written directly from colmap_help_3.9.1.txt and colmap_help_3.13.txt
# =============================================================================

CRITICAL_FLAGS_BY_SUBCOMMAND = {
    "feature_extractor": {"threads", "gpu", "max_image_size"},
    "sequential_matcher": {"threads", "gpu"},
    "exhaustive_matcher": {"threads", "gpu"},
    "vocab_tree_matcher": {"threads", "gpu"},
    "mapper": {"threads"},
}


def is_version_3_13_or_newer(version: Tuple[int, int, int]) -> bool:
    """Check if COLMAP version is 3.12+ / 3.13+."""
    return version >= (3, 12, 0)


def build_feature_extractor_args(
    version: Tuple[int, int, int],
    database_path: str,
    image_path: str,
    camera_model: str = "SIMPLE_RADIAL",
    single_camera: bool = True,
    max_image_size: int = 2000,
    use_gpu: bool = True,
    threads: int = 4,
    supported_flags: Optional[Set[str]] = None,
) -> List[str]:
    """
    Build CLI args for colmap feature_extractor across COLMAP versions.
    Asserts critical flags (threads, GPU, max_image_size) are mapped and retained.
    """
    args = [
        "--database_path", str(database_path),
        "--image_path", str(image_path),
        "--ImageReader.camera_model", str(camera_model),
        "--ImageReader.single_camera", "1" if single_camera else "0",
    ]

    is_v313 = is_version_3_13_or_newer(version)

    # 1. max_image_size (SiftExtraction.max_image_size in both 3.9 and 3.13)
    args.extend(["--SiftExtraction.max_image_size", str(max_image_size)])

    # 2. use_gpu
    if is_v313:
        gpu_flag = "--FeatureExtraction.use_gpu"
    else:
        gpu_flag = "--SiftExtraction.use_gpu"
    args.extend([gpu_flag, "1" if use_gpu else "0"])

    # 3. num_threads
    if is_v313:
        thread_flag = "--FeatureExtraction.num_threads"
    else:
        thread_flag = "--SiftExtraction.num_threads"
    args.extend([thread_flag, str(threads)])

    # Validate against supported flags if provided
    if supported_flags is not None:
        _validate_critical_flags("feature_extractor", args, supported_flags, ["max_image_size", "use_gpu", "threads"])

    return args


def build_sequential_matcher_args(
    version: Tuple[int, int, int],
    database_path: str,
    use_gpu: bool = True,
    threads: int = 4,
    overlap: int = 25,
    quadratic_overlap: bool = True,
    loop_detection: bool = False,
    vocab_tree_path: Optional[str] = None,
    supported_flags: Optional[Set[str]] = None,
) -> List[str]:
    """
    Build CLI args for colmap sequential_matcher.
    In 3.13, sets BOTH --FeatureMatching.num_threads and --SequentialMatching.num_threads.
    """
    args = [
        "--database_path", str(database_path),
        "--SequentialMatching.overlap", str(overlap),
        "--SequentialMatching.quadratic_overlap", "1" if quadratic_overlap else "0",
    ]

    is_v313 = is_version_3_13_or_newer(version)

    # GPU flag
    if is_v313:
        gpu_flag = "--FeatureMatching.use_gpu"
    else:
        gpu_flag = "--SiftMatching.use_gpu"
    args.extend([gpu_flag, "1" if use_gpu else "0"])

    # Thread flags: on 3.13, set BOTH FeatureMatching and SequentialMatching threads!
    if is_v313:
        args.extend(["--FeatureMatching.num_threads", str(threads)])
        args.extend(["--SequentialMatching.num_threads", str(threads)])
    else:
        args.extend(["--SiftMatching.num_threads", str(threads)])

    # Loop detection & Vocab Tree
    if loop_detection:
        args.extend(["--SequentialMatching.loop_detection", "1"])
        if vocab_tree_path:
            args.extend(["--SequentialMatching.vocab_tree_path", str(vocab_tree_path)])
    else:
        args.extend(["--SequentialMatching.loop_detection", "0"])

    if supported_flags is not None:
        _validate_critical_flags("sequential_matcher", args, supported_flags, ["use_gpu", "threads"])

    return args


def build_exhaustive_matcher_args(
    version: Tuple[int, int, int],
    database_path: str,
    use_gpu: bool = True,
    threads: int = 4,
    block_size: int = 50,
    supported_flags: Optional[Set[str]] = None,
) -> List[str]:
    """Build CLI args for colmap exhaustive_matcher."""
    args = [
        "--database_path", str(database_path),
        "--ExhaustiveMatching.block_size", str(block_size),
    ]

    is_v313 = is_version_3_13_or_newer(version)

    if is_v313:
        args.extend(["--FeatureMatching.use_gpu", "1" if use_gpu else "0"])
        args.extend(["--FeatureMatching.num_threads", str(threads)])
    else:
        args.extend(["--SiftMatching.use_gpu", "1" if use_gpu else "0"])
        args.extend(["--SiftMatching.num_threads", str(threads)])

    if supported_flags is not None:
        _validate_critical_flags("exhaustive_matcher", args, supported_flags, ["use_gpu", "threads"])

    return args


def build_vocab_tree_matcher_args(
    version: Tuple[int, int, int],
    database_path: str,
    vocab_tree_path: str,
    use_gpu: bool = True,
    threads: int = 4,
    supported_flags: Optional[Set[str]] = None,
) -> List[str]:
    """
    Build CLI args for colmap vocab_tree_matcher.
    In 3.13, sets BOTH --FeatureMatching.num_threads and --VocabTreeMatching.num_threads.
    """
    args = [
        "--database_path", str(database_path),
        "--VocabTreeMatching.vocab_tree_path", str(vocab_tree_path),
    ]

    is_v313 = is_version_3_13_or_newer(version)

    if is_v313:
        args.extend(["--FeatureMatching.use_gpu", "1" if use_gpu else "0"])
        args.extend(["--FeatureMatching.num_threads", str(threads)])
        args.extend(["--VocabTreeMatching.num_threads", str(threads)])
    else:
        args.extend(["--SiftMatching.use_gpu", "1" if use_gpu else "0"])
        args.extend(["--SiftMatching.num_threads", str(threads)])

    if supported_flags is not None:
        _validate_critical_flags("vocab_tree_matcher", args, supported_flags, ["use_gpu", "threads"])

    return args


def build_mapper_args(
    version: Tuple[int, int, int],
    database_path: str,
    image_path: str,
    output_path: str,
    threads: int = 4,
    timeout_seconds: int = 1800,
    init_min_tri_angle: float = 8.0,
    filter_min_tri_angle: float = 1.5,
    ba_use_gpu: bool = False,
    custom_ba_iterations: Optional[Dict[str, int]] = None,
    supported_flags: Optional[Set[str]] = None,
) -> Tuple[List[str], int]:
    """
    Build CLI args for colmap mapper.
    - Hang protection:
      * On 3.13: uses --Mapper.max_runtime_seconds as the hang protection.
      * On 3.9.x: returns ToolRunner timeout to enforce hang protection.
      * Low Ceres iteration caps are avoided to maintain interior reconstruction quality.
    - ba_use_gpu: Optional flag on 3.13 (disabled by default).
    Returns (cli_args, tool_runner_timeout).
    """
    args = [
        "--database_path", str(database_path),
        "--image_path", str(image_path),
        "--output_path", str(output_path),
        "--Mapper.init_min_tri_angle", str(init_min_tri_angle),
        "--Mapper.filter_min_tri_angle", str(filter_min_tri_angle),
        "--Mapper.num_threads", str(threads),
    ]

    is_v313 = is_version_3_13_or_newer(version)

    if is_v313:
        # Hang protection via native COLMAP flag
        args.extend(["--Mapper.max_runtime_seconds", str(timeout_seconds)])
        tool_runner_timeout = timeout_seconds + 30  # Margin for COLMAP to finish writing

        # Optional GPU bundle adjustment (disabled by default)
        if ba_use_gpu:
            args.extend(["--Mapper.ba_use_gpu", "1"])
    else:
        # Hang protection via ToolRunner timeout on 3.9.x
        tool_runner_timeout = timeout_seconds

    # Ceres iterations: use custom if provided, otherwise preserve COLMAP's standard defaults
    if custom_ba_iterations:
        for k, v in custom_ba_iterations.items():
            args.extend([f"--Mapper.{k}", str(v)])

    if supported_flags is not None:
        _validate_critical_flags("mapper", args, supported_flags, ["threads"])

    return args, tool_runner_timeout


def map_colmap_option(
    subcommand: str,
    key: str,
    value: Any,
    version: Tuple[int, int, int],
    is_critical: bool = False,
    supported_flags: Optional[Set[str]] = None,
) -> List[str]:
    """
    Map a semantic option key to its version-appropriate COLMAP CLI flag(s).
    If is_critical is True (or key is in critical set) and the option cannot be mapped
    or is missing from supported_flags, raises ColmapFlagMappingError.
    """
    is_v313 = is_version_3_13_or_newer(version)
    val_str = str(value) if not isinstance(value, bool) else ("1" if value else "0")

    generated: List[str] = []

    if subcommand == "feature_extractor":
        if key in ("threads", "num_threads"):
            flag = "--FeatureExtraction.num_threads" if is_v313 else "--SiftExtraction.num_threads"
            generated = [flag, val_str]
        elif key in ("gpu", "use_gpu"):
            flag = "--FeatureExtraction.use_gpu" if is_v313 else "--SiftExtraction.use_gpu"
            generated = [flag, val_str]
        elif key == "max_image_size":
            generated = ["--SiftExtraction.max_image_size", val_str]
        elif key == "camera_model":
            generated = ["--ImageReader.camera_model", val_str]
        elif key == "single_camera":
            generated = ["--ImageReader.single_camera", val_str]
        elif key == "database_path":
            generated = ["--database_path", val_str]
        elif key == "image_path":
            generated = ["--image_path", val_str]

    elif subcommand == "sequential_matcher":
        if key in ("threads", "num_threads"):
            if is_v313:
                generated = [
                    "--FeatureMatching.num_threads", val_str,
                    "--SequentialMatching.num_threads", val_str,
                ]
            else:
                generated = ["--SiftMatching.num_threads", val_str]
        elif key in ("gpu", "use_gpu"):
            flag = "--FeatureMatching.use_gpu" if is_v313 else "--SiftMatching.use_gpu"
            generated = [flag, val_str]
        elif key == "overlap":
            generated = ["--SequentialMatching.overlap", val_str]
        elif key == "quadratic_overlap":
            generated = ["--SequentialMatching.quadratic_overlap", val_str]
        elif key == "loop_detection":
            generated = ["--SequentialMatching.loop_detection", val_str]
        elif key == "vocab_tree_path":
            generated = ["--SequentialMatching.vocab_tree_path", val_str]
        elif key == "database_path":
            generated = ["--database_path", val_str]

    elif subcommand == "exhaustive_matcher":
        if key in ("threads", "num_threads"):
            flag = "--FeatureMatching.num_threads" if is_v313 else "--SiftMatching.num_threads"
            generated = [flag, val_str]
        elif key in ("gpu", "use_gpu"):
            flag = "--FeatureMatching.use_gpu" if is_v313 else "--SiftMatching.use_gpu"
            generated = [flag, val_str]
        elif key == "block_size":
            generated = ["--ExhaustiveMatching.block_size", val_str]
        elif key == "database_path":
            generated = ["--database_path", val_str]

    elif subcommand == "vocab_tree_matcher":
        if key in ("threads", "num_threads"):
            if is_v313:
                generated = [
                    "--FeatureMatching.num_threads", val_str,
                    "--VocabTreeMatching.num_threads", val_str,
                ]
            else:
                generated = ["--SiftMatching.num_threads", val_str]
        elif key in ("gpu", "use_gpu"):
            flag = "--FeatureMatching.use_gpu" if is_v313 else "--SiftMatching.use_gpu"
            generated = [flag, val_str]
        elif key == "vocab_tree_path":
            generated = ["--VocabTreeMatching.vocab_tree_path", val_str]
        elif key == "database_path":
            generated = ["--database_path", val_str]

    elif subcommand == "mapper":
        if key in ("threads", "num_threads"):
            generated = ["--Mapper.num_threads", val_str]
        elif key == "max_runtime_seconds":
            if is_v313:
                generated = ["--Mapper.max_runtime_seconds", val_str]
            elif is_critical:
                raise ColmapFlagMappingError(
                    f"--Mapper.max_runtime_seconds is not supported on COLMAP {version[0]}.{version[1]}.{version[2]}"
                )
        elif key == "ba_use_gpu":
            if is_v313:
                generated = ["--Mapper.ba_use_gpu", val_str]
            elif is_critical:
                raise ColmapFlagMappingError(
                    f"--Mapper.ba_use_gpu is not supported on COLMAP {version[0]}.{version[1]}.{version[2]}"
                )
        elif key in ("init_min_tri_angle", "filter_min_tri_angle"):
            generated = [f"--Mapper.{key}", val_str]
        elif key in ("database_path", "image_path", "output_path"):
            generated = [f"--{key}", val_str]

    if not generated:
        critical_keys = CRITICAL_FLAGS_BY_SUBCOMMAND.get(subcommand, set())
        if is_critical or key in critical_keys:
            raise ColmapFlagMappingError(
                f"Critical option '{key}' cannot be mapped for subcommand '{subcommand}' on COLMAP {version[0]}.{version[1]}.{version[2]}"
            )
        return []

    if supported_flags is not None:
        flag_names = [f for f in generated if f.startswith("--")]
        for f in flag_names:
            if f not in supported_flags:
                if is_critical or key in CRITICAL_FLAGS_BY_SUBCOMMAND.get(subcommand, set()):
                    raise ColmapFlagMappingError(
                        f"Critical flag '{f}' mapped from '{key}' is not in supported flags for '{subcommand}'"
                    )

    return generated


def _validate_critical_flags(
    subcommand: str,
    args: List[str],
    supported_flags: Set[str],
    critical_semantic_keys: List[str],
) -> None:
    """
    Assert that all generated flags are valid and supported, and that critical flags
    are present in the generated args and supported by the target COLMAP version.
    Raises ColmapFlagMappingError if any critical flag is missing or dropped.
    """
    arg_flag_names = {a for a in args if a.startswith("--")}

    for flag in arg_flag_names:
        if flag not in supported_flags:
            raise ColmapFlagMappingError(
                f"Generated flag '{flag}' is not supported by COLMAP for subcommand '{subcommand}'."
            )

    # Verify that critical flags were indeed generated
    for key in critical_semantic_keys:
        # Check that at least one flag matching the critical key was included
        if key in ("threads", "num_threads"):
            if not any("num_threads" in f for f in arg_flag_names):
                raise ColmapFlagMappingError(f"Critical thread limit flag missing from args for {subcommand}")
        elif key in ("gpu", "use_gpu"):
            if not any("use_gpu" in f for f in arg_flag_names):
                raise ColmapFlagMappingError(f"Critical GPU flag missing from args for {subcommand}")
        elif key == "max_image_size":
            if not any("max_image_size" in f for f in arg_flag_names):
                raise ColmapFlagMappingError(f"Critical max_image_size flag missing from args for {subcommand}")



def configure_loop_detection(
    version: Tuple[int, int, int],
    custom_vocab_path: Optional[str] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, Optional[str], str]:
    """
    Determine loop detection strategy based on COLMAP version and available vocab tree.
    - 3.13+: auto-downloads FAISS vocabulary tree by default.
    - 3.9.x: requires a local vocab tree file. If none found, falls back with warning.

    Returns:
        (loop_detection_enabled, vocab_tree_path, log_message)
    """
    # 1. Check if a local file is explicitly specified and exists
    local_path = None
    if custom_vocab_path and Path(custom_vocab_path).is_file():
        local_path = str(Path(custom_vocab_path).resolve())
    else:
        env_path = os.environ.get("SCANFORGE_VOCAB_TREE_PATH")
        if env_path and Path(env_path).is_file():
            local_path = str(Path(env_path).resolve())

    if local_path:
        msg = f"[SfM] Loop detection enabled using local vocabulary tree: {local_path}"
        if log_cb:
            log_cb(msg)
        return True, local_path, msg

    # 2. No local file found: check version behavior
    if is_version_3_13_or_newer(version):
        msg = "[SfM] Loop detection enabled using COLMAP 3.13 auto-download FAISS vocabulary tree."
        if log_cb:
            log_cb(msg)
        return True, None, msg
    else:
        msg = (
            "[SfM] Warning: COLMAP 3.9.x requires a local vocabulary tree file for loop detection, "
            "but none was found (SCANFORGE_VOCAB_TREE_PATH not set or file missing). "
            "Falling back to sequential matching without loop detection."
        )
        if log_cb:
            log_cb(msg)
        return False, None, msg


def verify_rename_map_against_fixtures() -> Dict[str, Any]:
    """
    Ground-truth validation: Verifies that every single flag generated for COLMAP 3.9.1
    and COLMAP 3.13.0 exists in the respective real help output fixtures.
    """
    help_391 = load_colmap_help_fixture("3.9.1")
    help_313 = load_colmap_help_fixture("3.13")

    results = {
        "3.9.1": {},
        "3.13": {},
    }

    # Test 3.9.1
    v391 = (3, 9, 1)
    fe_391 = build_feature_extractor_args(v391, "db", "imgs", supported_flags=help_391["feature_extractor"])
    sm_391 = build_sequential_matcher_args(v391, "db", supported_flags=help_391["sequential_matcher"])
    em_391 = build_exhaustive_matcher_args(v391, "db", supported_flags=help_391["exhaustive_matcher"])
    vm_391 = build_vocab_tree_matcher_args(v391, "db", "/path/vocab", supported_flags=help_391["vocab_tree_matcher"])
    map_391, _ = build_mapper_args(v391, "db", "imgs", "out", supported_flags=help_391["mapper"])

    results["3.9.1"] = {
        "feature_extractor": fe_391,
        "sequential_matcher": sm_391,
        "exhaustive_matcher": em_391,
        "vocab_tree_matcher": vm_391,
        "mapper": map_391,
    }

    # Test 3.13.0
    v313 = (3, 13, 0)
    fe_313 = build_feature_extractor_args(v313, "db", "imgs", supported_flags=help_313["feature_extractor"])
    sm_313 = build_sequential_matcher_args(v313, "db", supported_flags=help_313["sequential_matcher"])
    em_313 = build_exhaustive_matcher_args(v313, "db", supported_flags=help_313["exhaustive_matcher"])
    vm_313 = build_vocab_tree_matcher_args(v313, "db", "/path/vocab", supported_flags=help_313["vocab_tree_matcher"])
    map_313, _ = build_mapper_args(v313, "db", "imgs", "out", ba_use_gpu=True, supported_flags=help_313["mapper"])

    results["3.13"] = {
        "feature_extractor": fe_313,
        "sequential_matcher": sm_313,
        "exhaustive_matcher": em_313,
        "vocab_tree_matcher": vm_313,
        "mapper": map_313,
    }

    return results
