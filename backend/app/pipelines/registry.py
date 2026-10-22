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
        )
        stages.extend([
            OpenMVSInterfaceStage(),
            OpenMVSDensifyStage(),
            OpenMVSRMeshStage(),
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
