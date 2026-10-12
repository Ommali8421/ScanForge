"""
Core Pipeline Abstractions
Defines Stage, Pipeline, JobContext, StageResult, and CancelToken.
"""

import hashlib
import json
import os
import signal
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional
from app.config import settings
from app.utils.logging import logger


class CancelToken:
    def __init__(self):
        self._cancelled = False
        self._active_pid: Optional[int] = None

    def cancel(self):
        self._cancelled = True
        if self._active_pid:
            try:
                if os.name == "nt":
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(self._active_pid)])
                else:
                    os.killpg(os.getpgid(self._active_pid), signal.SIGTERM)
            except Exception:
                try:
                    os.kill(self._active_pid, signal.SIGKILL)
                except Exception:
                    pass

    def is_cancelled(self) -> bool:
        return self._cancelled

    def set_active_pid(self, pid: Optional[int]):
        self._active_pid = pid

    def get_active_pid(self) -> Optional[int]:
        return self._active_pid


@dataclass
class JobContext:
    job_id: str
    workdir: Path
    params: Dict[str, Any]
    cancel_token: CancelToken
    progress_cb: Callable[[str, int, str], None]
    log_cb: Callable[[str], None]
    cumulative_scale: float = 1.0


@dataclass
class StageResult:
    success: bool
    output_files: List[Path] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    skipped_cache: bool = False


class Stage(ABC):
    name: str = "base_stage"
    weight: float = 1.0
    timeout_seconds: int = settings.SCANFORGE_STAGE_TIMEOUT
    declared_inputs: List[str] = []
    declared_outputs: List[str] = []

    def get_params_hash(self, ctx: JobContext) -> str:
        """Compute SHA-256 hash of relevant parameters for caching."""
        relevant = {
            "stage": self.name,
            "params": ctx.params,
            "scale": ctx.cumulative_scale
        }
        raw = json.dumps(relevant, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def is_cached(self, ctx: JobContext) -> bool:
        """Check if stage outputs exist and match cached parameter hash."""
        cache_marker = ctx.workdir / f".cache_{self.name}.json"
        if not cache_marker.exists():
            return False

        try:
            with open(cache_marker, "r") as f:
                data = json.load(f)
            if data.get("hash") != self.get_params_hash(ctx):
                return False
            
            # Check if declared output files exist
            for out_name in self.declared_outputs:
                if not (ctx.workdir / out_name).exists():
                    return False
            return True
        except Exception:
            return False

    def mark_cached(self, ctx: JobContext):
        """Save parameter hash after successful stage completion."""
        cache_marker = ctx.workdir / f".cache_{self.name}.json"
        try:
            with open(cache_marker, "w") as f:
                json.dump({"hash": self.get_params_hash(ctx), "timestamp": time.time()}, f)
        except Exception as e:
            logger.warning(f"Could not write cache marker for {self.name}: {e}")

    @abstractmethod
    def run(self, ctx: JobContext) -> StageResult:
        """Execute stage logic."""
        pass


class Pipeline:
    def __init__(self, scan_type: str, stages: List[Stage]):
        self.scan_type = scan_type
        self.stages = stages

    def run(self, ctx: JobContext):
        """Run all stages sequentially, computing proportional progress."""
        total_weight = sum(s.weight for s in self.stages) or 1.0
        accumulated_weight = 0.0

        for stage in self.stages:
            if ctx.cancel_token.is_cancelled():
                ctx.log_cb(f"[Pipeline] Job cancelled before stage '{stage.name}'.")
                return

            stage_start_pct = int((accumulated_weight / total_weight) * 100)
            ctx.progress_cb(stage.name, stage_start_pct, f"Starting stage: {stage.name}")

            if stage.is_cached(ctx):
                ctx.log_cb(f"[{stage.name}] Stage output found in cache with matching params. Skipping.")
                accumulated_weight += stage.weight
                continue

            # Run stage
            start_time = time.time()
            result = stage.run(ctx)

            if not result.success:
                raise RuntimeError(f"Stage '{stage.name}' failed.")

            stage.mark_cached(ctx)
            accumulated_weight += stage.weight
            stage_end_pct = int((accumulated_weight / total_weight) * 100)
            elapsed = time.time() - start_time
            ctx.progress_cb(stage.name, stage_end_pct, f"Completed stage {stage.name} in {elapsed:.1f}s")
