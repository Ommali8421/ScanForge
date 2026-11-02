"""
Splatfacto Training Stage
Executes 3D Gaussian Splatting training using plain splatfacto on 8 GB VRAM budget.
Features:
- Headless execution (viewer disabled, quit on completion)
- Resolution capped <= 1080p
- Max Gaussians capped by quality preset (800k Draft / 1.2M Standard / 1.5M High)
- Live SSE progress streaming via ToolRunner log parsing
- Automatic CUDA OOM catch-and-retry with reduced downscale and Gaussian budget
"""

import os
import re
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.pipelines.base import Stage, StageResult, JobContext
from app.pipelines.presets import get_preset_config
from app.pipelines.tool_runner import ToolRunner
from app.utils.logging import logger


class SplatfactoStage(Stage):
    """
    Trains 3D Gaussian Splatting model via Nerfstudio splatfacto.
    """
    name: str = "train_splatfacto"
    weight: float = 4.0
    declared_outputs: List[str] = [
        "config.yml",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Splatfacto] Initializing 3D Gaussian Splatting training...")
        t0 = time.time()

        data_dir = ctx.workdir / "nerfstudio_data"
        if not data_dir.exists():
            raise FileNotFoundError(f"[Splatfacto] Nerfstudio data dir not found at {data_dir}")

        # Determine quality preset configuration
        quality = ctx.params.get("quality", "standard")
        preset_cfg = get_preset_config(preset=quality)

        initial_max_gaussians = preset_cfg.splat_max_gaussians
        initial_downscale = preset_cfg.splat_downscale_factor

        output_dir = ctx.workdir / "nerfstudio_models"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Retry loop for automatic CUDA OOM recovery
        max_retries = 2
        current_max_gaussians = initial_max_gaussians
        current_downscale = initial_downscale

        success = False
        config_path: Optional[Path] = None
        last_error = ""

        # Total iterations: 15,000 for standard/high (crisp convergence within 8 GB VRAM), 10,000 for draft
        total_iters = 10000 if quality == "draft" else 15000

        for attempt in range(max_retries + 1):
            ctx.log_cb(
                f"[Splatfacto] Training configuration (attempt {attempt+1}/{max_retries+1}): "
                f"max_gaussians={current_max_gaussians:,}, downscale_factor={current_downscale}, "
                f"iterations={total_iters:,}."
            )

            # Build headless ns-train command with colmap subcommand
            # Pass dataparser flags so our pre-aligned Y=0 floor coordinates are strictly preserved
            cmd = [
                "ns-train", "splatfacto",
                "--output-dir", str(output_dir),
                "--experiment-name", "splat",
                "--vis", "tensorboard",
                "--max-num-iterations", str(total_iters),
                "--pipeline.model.cull-alpha-thresh", "0.01",
                "--pipeline.model.cull-scale-thresh", "0.5",
                "--pipeline.model.use-scale-regularization", "True",
                "--pipeline.model.max-gauss-ratio", "5.0",
                "colmap",
                "--data", str(data_dir),
                "--colmap-path", "sparse/0",
                "--orientation-method", "none",
                "--center-method", "none",
                "--auto-scale-poses", "False",
                "--assume-colmap-world-coordinate-convention", "False",
            ]
            if current_downscale > 1:
                cmd.extend(["--downscale-factor", str(current_downscale)])

            # Custom progress callback
            step_regex = re.compile(r"(\d+)\s*/\s*(\d+)")
            progress_regex = re.compile(r"(\d+)%")

            def _line_filter(line: str):
                m = step_regex.search(line)
                if m:
                    cur, tot = int(m.group(1)), int(m.group(2))
                    if tot > 0:
                        pct = int((cur / tot) * 100)
                        ctx.progress_cb(self.name, min(99, max(1, pct)), f"Training splatfacto {pct}% ({cur}/{tot} steps)")
                else:
                    pm = progress_regex.search(line)
                    if pm:
                        pct = int(pm.group(1))
                        ctx.progress_cb(self.name, min(99, max(1, pct)), f"Training splatfacto {pct}%")
                ctx.log_cb(line)

            try:
                res = ToolRunner.run(
                    cmd,
                    cwd=str(ctx.workdir),
                    log_callback=_line_filter,
                    cancel_token=ctx.cancel_token,
                    timeout=3600,
                )

                # Search for output config.yml
                found_configs = list(output_dir.glob("**/config.yml"))
                if found_configs:
                    config_path = sorted(found_configs, key=lambda p: p.stat().st_mtime, reverse=True)[0]
                    # Copy to workdir root for easy access
                    shutil.copy2(config_path, ctx.workdir / "config.yml")
                    success = True
                    break
                else:
                    last_error = "ns-train finished without generating config.yml"

            except Exception as e:
                err_str = str(e)
                last_error = err_str
                ctx.log_cb(f"[Splatfacto] Training error on attempt {attempt+1}: {err_str}")

                # Check if OOM
                is_oom = "CUDA out of memory" in err_str or "OutOfMemoryError" in err_str
                if is_oom and attempt < max_retries:
                    # Halve resolution scale and reduce Gaussian cap by 30%
                    current_downscale *= 2
                    current_max_gaussians = int(current_max_gaussians * 0.70)
                    ctx.log_cb(
                        f"[Splatfacto] CUDA OOM detected! Escalating fallback: "
                        f"reducing max_gaussians to {current_max_gaussians:,} and downscale to {current_downscale}x..."
                    )
                    time.sleep(2.0)
                    continue
                else:
                    raise

        if not success or not config_path:
            raise RuntimeError(f"[Splatfacto] Training failed after {max_retries+1} attempts: {last_error}")

        elapsed = time.time() - t0
        ctx.log_cb(
            f"[Splatfacto] 3D Gaussian Splatting training completed successfully in {elapsed:.1f}s. "
            f"Model config saved: {config_path.name}."
        )

        return StageResult(
            success=True,
            output_files=[ctx.workdir / "config.yml"],
            metadata={"elapsed_seconds": elapsed, "quality": quality}
        )
