"""
Quality Presets and VRAM-Aware Parameter Tuning
Implements Portability Rule 4:
Quality presets read available GPU memory (env SCANFORGE_VRAM_GB or nvidia-smi)
instead of hardcoding an 8 GB assumption, with the 8 GB preset as the default baseline.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from app.utils.tool_resolve import get_available_vram_gb


@dataclass
class QualityPresetConfig:
    preset_name: str
    vram_gb: float
    colmap_max_image_size: int
    openmvs_resolution_level: int
    openmvs_max_faces: int
    splat_max_gaussians: int
    splat_downscale_factor: int


def get_preset_config(preset: str = "standard", vram_gb: Optional[float] = None) -> QualityPresetConfig:
    """
    Compute dynamic tuning parameters for a given quality preset and VRAM budget.
    Default baseline assumes 8.0 GB VRAM.
    """
    vram = vram_gb if vram_gb is not None else get_available_vram_gb()
    p = (preset or "standard").lower()

    if vram >= 12.0:
        # High-end GPU (12+ GB VRAM)
        if p == "draft":
            return QualityPresetConfig(
                preset_name="draft",
                vram_gb=vram,
                colmap_max_image_size=1800,
                openmvs_resolution_level=2,
                openmvs_max_faces=100000,
                splat_max_gaussians=1000000,
                splat_downscale_factor=2
            )
        elif p == "high":
            return QualityPresetConfig(
                preset_name="high",
                vram_gb=vram,
                colmap_max_image_size=3200,
                openmvs_resolution_level=1,
                openmvs_max_faces=500000,
                splat_max_gaussians=2500000,
                splat_downscale_factor=1
            )
        else:  # standard
            return QualityPresetConfig(
                preset_name="standard",
                vram_gb=vram,
                colmap_max_image_size=2400,
                openmvs_resolution_level=1,
                openmvs_max_faces=250000,
                splat_max_gaussians=1500000,
                splat_downscale_factor=1
            )

    elif vram >= 7.5:
        # 8 GB baseline (RTX 4060 target)
        if p == "draft":
            return QualityPresetConfig(
                preset_name="draft",
                vram_gb=vram,
                colmap_max_image_size=1600,
                openmvs_resolution_level=2,
                openmvs_max_faces=100000,
                splat_max_gaussians=800000,
                splat_downscale_factor=2
            )
        elif p == "high":
            return QualityPresetConfig(
                preset_name="high",
                vram_gb=vram,
                colmap_max_image_size=2400,
                openmvs_resolution_level=1,
                openmvs_max_faces=350000,
                splat_max_gaussians=1500000,
                splat_downscale_factor=1
            )
        else:  # standard
            return QualityPresetConfig(
                preset_name="standard",
                vram_gb=vram,
                colmap_max_image_size=2000,
                openmvs_resolution_level=2,
                openmvs_max_faces=200000,
                splat_max_gaussians=1200000,
                splat_downscale_factor=1
            )

    else:
        # Constrained GPU (<8 GB VRAM)
        if p == "draft":
            return QualityPresetConfig(
                preset_name="draft",
                vram_gb=vram,
                colmap_max_image_size=1200,
                openmvs_resolution_level=3,
                openmvs_max_faces=50000,
                splat_max_gaussians=500000,
                splat_downscale_factor=4
            )
        elif p == "high":
            return QualityPresetConfig(
                preset_name="high",
                vram_gb=vram,
                colmap_max_image_size=1800,
                openmvs_resolution_level=2,
                openmvs_max_faces=150000,
                splat_max_gaussians=1000000,
                splat_downscale_factor=2
            )
        else:  # standard
            return QualityPresetConfig(
                preset_name="standard",
                vram_gb=vram,
                colmap_max_image_size=1600,
                openmvs_resolution_level=2,
                openmvs_max_faces=100000,
                splat_max_gaussians=800000,
                splat_downscale_factor=2
            )
