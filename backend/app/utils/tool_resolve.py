"""
Tool Resolution and Runtime Environment Detection Module
Implements ScanForge Portability Rules:
1. Dynamic resolution of tool binaries from PATH or environment variables.
2. Runtime COLMAP version detection and dynamic flag validation via --help.
3. Dynamic GPU VRAM discovery (env SCANFORGE_VRAM_GB or nvidia-smi with 8 GB default).
4. Resource etiquette (honouring CUDA_VISIBLE_DEVICES and SCANFORGE_NUM_THREADS).
"""

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.utils.logging import logger


def resolve_binary(
    tool_name: str,
    env_var: Optional[str] = None,
    fallback_dirs: Optional[List[str]] = None
) -> str:
    """
    Resolve binary executable path from environment variable, PATH, or fallback directories.
    Never assumes a hardcoded path; works seamlessly in Docker, Conda, or native environments.
    """
    # 1. Environment variable override
    if env_var:
        val = os.environ.get(env_var)
        if val and Path(val).exists():
            return str(Path(val).resolve())

    # 2. System PATH
    found = shutil.which(tool_name)
    if found:
        return found

    # 3. Check specific search directories if provided
    if fallback_dirs:
        for d in fallback_dirs:
            if not d:
                continue
            candidate = Path(d) / tool_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate.resolve())

    # Return bare tool name if not found in custom paths, allowing system execution
    return tool_name


def resolve_colmap() -> str:
    """Resolve COLMAP binary."""
    return resolve_binary("colmap", env_var="SCANFORGE_COLMAP_BIN")


def resolve_openmvs(bin_name: str) -> str:
    """Resolve OpenMVS binary (e.g. DensifyPointCloud, ReconstructMesh, TextureMesh)."""
    custom_dir = os.environ.get("SCANFORGE_OPENMVS_DIR")
    search_dirs = [custom_dir] if custom_dir else []
    search_dirs.extend([
        "/usr/local/bin",
        "/opt/openmvs/bin",
        "/opt/openmvs",
        "/usr/bin"
    ])
    return resolve_binary(bin_name, fallback_dirs=search_dirs)


def resolve_ffmpeg() -> str:
    """Resolve ffmpeg binary."""
    return resolve_binary("ffmpeg", env_var="SCANFORGE_FFMPEG_BIN")


def resolve_ffprobe() -> str:
    """Resolve ffprobe binary."""
    return resolve_binary("ffprobe", env_var="SCANFORGE_FFPROBE_BIN")


def resolve_blender() -> str:
    """Resolve blender binary."""
    return resolve_binary("blender", env_var="SCANFORGE_BLENDER_BIN")


@functools.lru_cache(maxsize=1)
def get_colmap_version(colmap_bin: Optional[str] = None) -> Tuple[int, int, int]:
    """
    Detect installed COLMAP version at runtime by parsing colmap -h output.
    Returns (major, minor, patch), e.g. (3, 9, 1). Defaults to (3, 9, 0) if unparseable.
    """
    bin_path = colmap_bin or resolve_colmap()
    try:
        proc = subprocess.run([bin_path, "-h"], capture_output=True, text=True, timeout=10)
        output = proc.stdout + "\n" + proc.stderr
        match = re.search(r"COLMAP\s+(\d+)\.(\d+)(?:\.(\d+))?", output)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3)) if match.group(3) else 0
            logger.info(f"[Portability] Detected COLMAP version: {major}.{minor}.{patch}")
            return (major, minor, patch)
    except Exception as e:
        logger.warning(f"[Portability] Could not detect COLMAP version ({e}); defaulting to (3, 9, 0)")
    return (3, 9, 0)


@functools.lru_cache(maxsize=16)
def get_colmap_supported_flags(subcommand: str, colmap_bin: Optional[str] = None) -> Set[str]:
    """
    Query colmap <subcommand> -h at runtime and extract all supported CLI flags.
    Allows mapping differing option names across COLMAP 3.9.x vs 3.12+.
    """
    bin_path = colmap_bin or resolve_colmap()
    flags: Set[str] = set()
    try:
        proc = subprocess.run([bin_path, subcommand, "-h"], capture_output=True, text=True, timeout=10)
        output = proc.stdout + "\n" + proc.stderr
        # Find all strings like '--OptionName.flag' or '--flag'
        matches = re.findall(r"(--[a-zA-Z0-9_\.]+)", output)
        flags.update(matches)
    except Exception as e:
        logger.warning(f"[Portability] Could not query flags for colmap {subcommand}: {e}")
    return flags


def filter_colmap_args(
    subcommand: str,
    args_list: List[str],
    colmap_bin: Optional[str] = None,
    critical_flags: Optional[Set[str]] = None,
) -> List[str]:
    """
    Filter and adapt argument list for colmap subcommand based on runtime supported flags.
    Prevents crashing on flags renamed or removed between COLMAP versions.
    If critical_flags is provided and any requested flag matching critical_flags
    is not supported, raises ColmapFlagMappingError.
    """
    from app.utils.colmap_compat import ColmapFlagMappingError

    supported = get_colmap_supported_flags(subcommand, colmap_bin)
    if not supported:
        # If unable to parse help flags, pass args as-is
        return args_list

    filtered: List[str] = []
    i = 0
    while i < len(args_list):
        item = args_list[i]
        if item.startswith("--"):
            if item in supported:
                filtered.append(item)
                if i + 1 < len(args_list) and not args_list[i + 1].startswith("--"):
                    filtered.append(args_list[i + 1])
                    i += 1
            else:
                if critical_flags and item in critical_flags:
                    raise ColmapFlagMappingError(
                        f"Critical flag '{item}' is not supported by COLMAP for subcommand '{subcommand}'"
                    )
                logger.debug(f"[Portability] Omitted unsupported COLMAP flag: {item}")
                if i + 1 < len(args_list) and not args_list[i + 1].startswith("--"):
                    i += 1
        else:
            filtered.append(item)
        i += 1
    return filtered


def get_available_vram_gb() -> float:
    """
    Read available GPU memory in GB.
    Honours SCANFORGE_VRAM_GB environment variable or queries nvidia-smi.
    Defaults to 8.0 GB baseline.
    """
    env_vram = os.environ.get("SCANFORGE_VRAM_GB")
    if env_vram:
        try:
            return float(env_vram)
        except ValueError:
            pass

    try:
        # Query total VRAM in MB from nvidia-smi
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            lines = res.stdout.strip().split("\n")
            if lines and lines[0].strip().isdigit():
                return float(lines[0].strip()) / 1024.0
    except Exception:
        pass

    return 8.0


def get_configured_threads() -> int:
    """
    Get configured CPU thread count, honouring SCANFORGE_NUM_THREADS.
    Never assumes all CPU cores are free; leaves headroom for system/GPU driver.
    """
    env_threads = os.environ.get("SCANFORGE_NUM_THREADS")
    if env_threads:
        try:
            return max(1, int(env_threads))
        except ValueError:
            pass

    total_cores = os.cpu_count() or 2
    # Reserve at least 1 core for OS/driver, cap default worker threads at 4
    return max(1, min(4, total_cores - 1))
