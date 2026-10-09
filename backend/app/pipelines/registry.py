"""
Pipeline Registry
Resolves appropriate Pipeline instance given scan type and active engine mode.
"""

from typing import Dict, Any
from app.pipelines.base import Pipeline
from app.pipelines.mock import create_mock_pipeline
from app.config import settings


class PipelineRegistry:
    @staticmethod
    def get_pipeline(scan_type: str, engine_mode: str | None = None) -> Pipeline:
        mode = engine_mode or settings.SCANFORGE_ENGINE
        if mode == "mock":
            return create_mock_pipeline(scan_type)

        # For real engine mode: fallback to mock in P0/P1 before real stages are compiled
        return create_mock_pipeline(scan_type)


pipeline_registry = PipelineRegistry()
