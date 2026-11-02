"""
Splat Export Stage
Exports canonical 3D Gaussian Splatting PLY file from trained Nerfstudio model
using `ns-export gaussian-splat`.
"""

import shutil
import time
from pathlib import Path
from typing import Dict, Any, List

from app.pipelines.base import Stage, StageResult, JobContext
from app.pipelines.tool_runner import ToolRunner
from app.utils.logging import logger


class SplatExportStage(Stage):
    """
    Exports trained 3DGS model into canonical PLY point cloud representation.
    """
    name: str = "export_splat"
    weight: float = 1.0
    declared_outputs: List[str] = [
        "splat.ply",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[SplatExport] Exporting canonical 3DGS PLY from trained model...")
        t0 = time.time()

        config_file = ctx.workdir / "config.yml"
        if not config_file.exists():
            # Check nerfstudio_models
            configs = list(ctx.workdir.glob("**/config.yml"))
            if configs:
                config_file = configs[0]
            else:
                raise FileNotFoundError(f"[SplatExport] config.yml missing in {ctx.workdir}")

        export_dir = ctx.workdir / "splat_export"
        export_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ns-export", "gaussian-splat",
            "--load-config", str(config_file),
            "--output-dir", str(export_dir),
        ]

        ctx.log_cb(f"[SplatExport] Executing: {' '.join(cmd)}")
        res = ToolRunner.run(
            cmd,
            cwd=str(ctx.workdir),
            log_callback=ctx.log_cb,
            cancel_token=ctx.cancel_token,
            timeout=600,
        )

        # Look for exported .ply in export_dir
        ply_files = list(export_dir.glob("*.ply"))
        if not ply_files:
            # Fallback check
            ply_files = list(ctx.workdir.glob("splat_export/**/*.ply"))

        if not ply_files:
            raise FileNotFoundError(f"[SplatExport] ns-export did not generate .ply file in {export_dir}")

        exported_ply = ply_files[0]
        canonical_ply = ctx.workdir / "splat.ply"
        shutil.copy2(exported_ply, canonical_ply)

        elapsed = time.time() - t0
        ctx.log_cb(
            f"[SplatExport] Canonical 3DGS PLY exported successfully ({canonical_ply.stat().st_size:,} bytes) "
            f"in {elapsed:.1f}s."
        )

        return StageResult(
            success=True,
            output_files=[canonical_ply],
            metadata={"elapsed_seconds": elapsed, "file_size": canonical_ply.stat().st_size}
        )
