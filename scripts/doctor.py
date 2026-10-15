#!/usr/bin/env python3
"""
ScanForge System Doctor (scripts/doctor.py)
Validates local and container environment, GPU access, disk space, and tooling dependencies.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import shutil
import subprocess
import sys
from pathlib import Path


# Configure utf-8 stdout if available
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def print_status(component: str, ok: bool, details: str = "", hint: str = ""):
    symbol = "[OK]" if ok else "[WARN]"
    msg = f"{symbol} [{component}]: {details}" if details else f"{symbol} [{component}]"
    print(msg)
    if not ok and hint:
        print(f"   -> Hint: {hint}")



def check_workspace_path():
    cwd = Path.cwd().resolve().as_posix()
    is_mnt_c = cwd.startswith("/mnt/c")
    if is_mnt_c:
        print_status(
            "Workspace Location",
            False,
            f"Running under {cwd}",
            "Move project to WSL native filesystem (e.g., ~/scanforge) for required I/O performance."
        )
    else:
        print_status("Workspace Location", True, f"{cwd}")


def check_disk_space():
    host_c = Path("/mnt/c")
    if host_c.exists():
        total, used, free = shutil.disk_usage(host_c)
        free_gb = free / (1024 ** 3)
        ok = free_gb >= 40.0
        print_status(
            "Host Disk Space (/mnt/c)",
            ok,
            f"{free_gb:.1f} GB free",
            "Free up at least 40 GB of storage for photogrammetry point clouds and intermediate meshes."
        )
    else:
        # Inside a container or non-WSL: report overlay/virtual disk, clearly labeled
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024 ** 3)
        print_status(
            "Container/WSL virtual disk (not host free space)",
            True,  # informational only — cannot assess host disk from inside container
            f"{free_gb:.1f} GB free on overlay/virtual disk",
            "Run doctor.py on the WSL host (not inside a container) to check actual host disk space."
        )


def check_command(name: str, cmd: list[str], hint: str = "", critical: bool = False):
    found = shutil.which(cmd[0]) is not None
    if not found:
        print_status(name, False, "Not found in PATH", hint)
        return False
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        ok = (res.returncode == 0) or ("OpenMVS" in res.stdout)
        details = res.stdout.splitlines()[0] if res.stdout else "Available"
        print_status(name, ok, details, hint)
        return ok
    except Exception as e:
        print_status(name, False, f"Failed to execute ({e})", hint)
        return False


def check_nvidia_gpu():
    has_smi = shutil.which("nvidia-smi") is not None
    if not has_smi:
        print_status(
            "NVIDIA GPU / Driver",
            False,
            "nvidia-smi not detected",
            "Ensure NVIDIA drivers and WSL2 GPU passthrough are installed if running GPU mode."
        )
        return

    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5
        ).strip()
        lines = output.splitlines()
        for idx, line in enumerate(lines):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name, total_mb, free_mb = parts[0], float(parts[1]), float(parts[2])
                vram_gb = free_mb / 1024.0
                ok = vram_gb >= 6.0
                print_status(
                    f"GPU {idx} ({name})",
                    ok,
                    f"{vram_gb:.1f} GB VRAM free / {total_mb/1024.0:.1f} GB total",
                    "Close VRAM-heavy applications before starting large reconstruction jobs."
                )
    except Exception as e:
        print_status("NVIDIA GPU", False, f"Failed querying nvidia-smi: {e}")


def check_colmap():
    cmd = ["colmap", "--help"]
    found = shutil.which(cmd[0]) is not None
    if not found:
        print_status("COLMAP (with CUDA)", False, "Not found in PATH", "COLMAP is required for real GPU photogrammetry.")
        return False
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        ok = res.returncode == 0
        details = res.stdout.splitlines()[0] if res.stdout else "Available"
        
        # Check if CUDA is enabled in the binary
        has_cuda = False
        try:
            colmap_path = shutil.which("colmap")
            if colmap_path:
                ldd_res = subprocess.run(["ldd", colmap_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if "cuda" in ldd_res.stdout.lower() or "cudart" in ldd_res.stdout.lower():
                    has_cuda = True
        except Exception:
            pass

        cuda_suffix = " (CUDA enabled)" if has_cuda else ""
        print_status("COLMAP (with CUDA)", ok and (has_cuda or shutil.which("ldd") is None), f"{details}{cuda_suffix}", "Ensure COLMAP is built with CUDA support.")
        return ok
    except Exception as e:
        print_status("COLMAP (with CUDA)", False, f"Failed to execute ({e})")
        return False


def main():
    print("=" * 60)
    print(" ScanForge Environment Diagnostics (doctor.py)")
    print("=" * 60)

    print("\n--- System & Environment ---")
    check_workspace_path()
    check_disk_space()
    check_nvidia_gpu()

    print("\n--- Tooling & Binaries ---")
    check_command("FFmpeg", ["ffmpeg", "-version"], "Install ffmpeg for video frame extraction.")
    check_colmap()
    check_command("OpenMVS InterfaceCOLMAP", ["InterfaceCOLMAP", "--help"], "OpenMVS InterfaceCOLMAP is required for real GPU photogrammetry.")
    check_command("OpenMVS DensifyPointCloud", ["DensifyPointCloud", "--help"], "OpenMVS DensifyPointCloud is required for real GPU photogrammetry.")
    check_command("OpenMVS ReconstructMesh", ["ReconstructMesh", "--help"], "OpenMVS ReconstructMesh is required for real GPU photogrammetry.")
    check_command("OpenMVS TextureMesh", ["TextureMesh", "--help"], "OpenMVS TextureMesh is required for real GPU photogrammetry.")
    check_command("Blender", ["blender", "--version"], "Blender is required for FBX/USDZ conversions.")

    print("\n--- Python Environment ---")
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        cuda_dev = torch.cuda.get_device_name(0) if cuda_avail else "N/A"
        print_status("PyTorch", True, f"v{torch.__version__} (CUDA: {cuda_avail}, Device: {cuda_dev})")
    except ImportError:
        print_status("PyTorch", False, "Not installed in active Python environment", "Install via pip in worker environment.")

    try:
        import open3d
        print_status("Open3D", True, f"v{open3d.__version__}")
    except ImportError:
        print_status("Open3D", False, "Not installed in active Python environment", "Install open3d for mesh post-processing.")

    try:
        import trimesh
        print_status("Trimesh", True, f"v{trimesh.__version__}")
    except ImportError:
        print_status("Trimesh", False, "Not installed in active Python environment", "Install trimesh for format exports.")

    print("=" * 60)
    print("Doctor check complete.")


if __name__ == "__main__":
    main()
