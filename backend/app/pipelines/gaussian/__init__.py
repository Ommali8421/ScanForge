"""
3D Gaussian Splatting (3DGS) Pipeline
Milestone P3
"""

from app.pipelines.gaussian.pre_align import PreTrainFloorAlignStage
from app.pipelines.gaussian.train_splatfacto import SplatfactoStage
from app.pipelines.gaussian.export_splat import SplatExportStage
from app.pipelines.gaussian.splat_cleanup import SplatCleanupStage
from app.pipelines.gaussian.format_converter import SplatFormatConverterStage
from app.pipelines.gaussian.splat_mesher import SplatMesherStage

__all__ = [
    "PreTrainFloorAlignStage",
    "SplatfactoStage",
    "SplatExportStage",
    "SplatCleanupStage",
    "SplatFormatConverterStage",
    "SplatMesherStage",
]
