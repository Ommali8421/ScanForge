"""
Capabilities API Route
Dynamically determines runtime converters, supported formats, and engine limits.
"""

import shutil
from fastapi import APIRouter
from app.config import settings
from app.models.schemas import CapabilitiesResponse

router = APIRouter(prefix="/capabilities", tags=["system"])


def check_blender_available() -> bool:
    """Detect if headless Blender executable is present in environment PATH."""
    return shutil.which("blender") is not None


def check_gpu_available() -> bool:
    """Check if CUDA GPU is available via PyTorch or nvidia-smi."""
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    return shutil.which("nvidia-smi") is not None


@router.get("", response_model=CapabilitiesResponse)
def get_capabilities():
    blender_ok = check_blender_available()
    gpu_ok = check_gpu_available()

    # Base mesh formats supported by default
    mesh_formats = ["glb", "obj", "ply", "stl", "xyz"]
    if blender_ok:
        mesh_formats.extend(["fbx", "usdz"])

    splat_formats = ["ply", "splat"]
    lidar_formats = ["glb", "ply", "xyz"]
    if blender_ok:
        lidar_formats.extend(["fbx", "usdz"])

    format_matrix = {
        "photo": mesh_formats,
        "gaussian_splat": splat_formats,
        "lidar": lidar_formats,
    }

    scan_types = ["photo", "gaussian_splat", "lidar"]

    return CapabilitiesResponse(
        engine=settings.SCANFORGE_ENGINE,
        gpu_available=gpu_ok,
        scan_types=scan_types,
        lidar_enabled=settings.ENABLE_LIDAR,
        quality_presets=["draft", "standard", "high"],
        mesh_routes=["auto", "photogrammetry", "depth_fusion"],
        format_matrix=format_matrix,
        runtime_converters={
            "blender": blender_ok,
            "fbx_supported": blender_ok,
            "usdz_supported": blender_ok,
        },
        limits={
            "max_upload_mb": settings.SCANFORGE_MAX_UPLOAD_MB,
            "max_video_seconds": settings.SCANFORGE_MAX_VIDEO_SECONDS,
            "max_frames_photo": settings.SCANFORGE_MAX_FRAMES_PHOTO,
            "max_frames_3dgs": settings.SCANFORGE_MAX_FRAMES_3DGS,
        }
    )
