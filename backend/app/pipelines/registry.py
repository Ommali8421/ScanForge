"""
Pipeline Registry
Resolves appropriate Pipeline instance given scan type and active engine mode.
"""

from typing import Dict, Any
from app.pipelines.base import Pipeline
from app.pipelines.mock import create_mock_pipeline
from app.config import settings


def create_real_pipeline(scan_type: str) -> Pipeline:
    """Build real GPU pipeline stages for milestone P2c Phase 1."""
    from app.pipelines.common.ingest import IngestStage
    from app.pipelines.common.frame_extraction import FrameExtractionStage
    from app.pipelines.common.sfm_colmap import ColmapSfMStage

    stages = [
        IngestStage(),
        FrameExtractionStage(),
        ColmapSfMStage()
    ]

    if scan_type == "photo":
        from app.pipelines.photo.openmvs import (
            OpenMVSInterfaceStage,
            OpenMVSDensifyStage,
            OpenMVSRMeshStage,
            OpenMVSTextureStage,
        )
        from app.pipelines.depth import (
            MonocularDepthStage,
            DepthAlignStage,
            TSDFFusionStage,
        )
        from app.pipelines.mesh import (
            RouteClassifierStage,
            MeshCleanupStage,
            RoomAnalysisStage,
            PlaneRepairStage,
            DecimateStage,
            PoissonABStage,
            FloorAlignAndScaleStage,
            FloorPlanStage,
            MeshExportStage,
            QualityReportStage,
        )
        stages.extend([
            RouteClassifierStage(),
            OpenMVSInterfaceStage(),
            OpenMVSDensifyStage(),
            OpenMVSRMeshStage(),
            MonocularDepthStage(),
            DepthAlignStage(),
            TSDFFusionStage(),
            MeshCleanupStage(),
            RoomAnalysisStage(),
            PlaneRepairStage(),
            DecimateStage(),
            OpenMVSTextureStage(),
            PoissonABStage(),
            FloorAlignAndScaleStage(),
            FloorPlanStage(),
            MeshExportStage(),
            QualityReportStage(),
        ])
    elif scan_type in ("gaussian_splat", "3dgs"):
        from app.pipelines.mesh.room_analysis import RoomAnalysisStage
        from app.pipelines.gaussian import (
            PreTrainFloorAlignStage,
            SplatfactoStage,
            SplatExportStage,
            SplatCleanupStage,
            SplatFormatConverterStage,
            SplatMesherStage,
        )
        from app.pipelines.mesh import (
            MeshCleanupStage,
            PlaneRepairStage,
            DecimateStage,
            FloorAlignAndScaleStage,
            FloorPlanStage,
            MeshExportStage,
            QualityReportStage,
        )
        from app.pipelines.photo.openmvs import OpenMVSTextureStage

        stages.extend([
            RoomAnalysisStage(),
            PreTrainFloorAlignStage(),
            SplatfactoStage(),
            SplatExportStage(),
            SplatCleanupStage(),
            SplatFormatConverterStage(),
            SplatMesherStage(),
            MeshCleanupStage(),
            PlaneRepairStage(),
            DecimateStage(),
            OpenMVSTextureStage(),
            FloorAlignAndScaleStage(),
            FloorPlanStage(),
            MeshExportStage(),
            QualityReportStage(),
        ])

    return Pipeline(scan_type=scan_type, stages=stages)


class PipelineRegistry:
    @staticmethod
    def get_pipeline(scan_type: str, engine_mode: str | None = None) -> Pipeline:
        mode = engine_mode or settings.SCANFORGE_ENGINE
        if mode == "mock":
            return create_mock_pipeline(scan_type)
        return create_real_pipeline(scan_type)


pipeline_registry = PipelineRegistry()
