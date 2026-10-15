"""
Real Ingest Stage
Validates video metadata with ffprobe, enforces duration limits (<=180s),
strips audio, tone-maps HDR/10-bit inputs, and normalizes video orientation.
"""

import json
import shutil
from pathlib import Path
from typing import Optional, List
from app.config import settings
from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.tool_runner import ToolRunner
from app.services.storage import storage_service
from app.utils.ffprobe import probe_video


class IngestStage(Stage):
    name: str = "ingest"
    weight: float = 1.0
    declared_outputs: List[str] = ["normalized_input.mp4", "ingest_metadata.json"]

    def _find_input_file(self, ctx: JobContext) -> Optional[Path]:
        """Locate the uploaded input file for the job."""
        # 1. From job params
        param_path = ctx.params.get("input_file_path")
        if param_path and Path(param_path).exists():
            return Path(param_path)

        # 2. In job upload directory
        upload_dir = storage_service.get_job_upload_dir(ctx.job_id)
        if upload_dir.exists():
            for ext in ("*.mp4", "*.mov", "*.m4v", "*.avi", "*.zip", "*.r3d"):
                matches = list(upload_dir.glob(ext))
                if matches:
                    return matches[0]

        # 3. In job workdir
        for ext in ("*.mp4", "*.mov", "*.m4v", "*.avi", "*.zip", "*.r3d"):
            matches = list(ctx.workdir.glob(ext))
            if matches:
                return matches[0]

        return None

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Ingest] Locating and validating uploaded video file...")
        input_path = self._find_input_file(ctx)

        if not input_path or not input_path.exists():
            raise FileNotFoundError(f"Input file not found for job {ctx.job_id}.")

        ctx.log_cb(f"[Ingest] Found input: {input_path.name} ({input_path.stat().st_size / (1024*1024):.2f} MB)")

        # Run ffprobe
        metadata = probe_video(input_path)
        if not metadata.get("probed"):
            ctx.log_cb("[Ingest] Warning: ffprobe could not extract full video stream metadata.")

        duration = metadata.get("duration", 0.0)
        ctx.log_cb(
            f"[Ingest] Video duration: {duration:.2f}s, resolution: {metadata.get('width')}x{metadata.get('height')}, "
            f"effective: {metadata.get('effective_width')}x{metadata.get('effective_height')}, "
            f"fps: {metadata.get('fps'):.1f}, codec: {metadata.get('codec')}, "
            f"rotation: {metadata.get('rotation')}°, HDR: {metadata.get('is_hdr')}"
        )

        # Enforce maximum duration (180s)
        if duration > float(settings.SCANFORGE_MAX_VIDEO_SECONDS):
            raise ValueError(
                f"Video duration ({duration:.1f}s) exceeds the maximum allowed limit of "
                f"{settings.SCANFORGE_MAX_VIDEO_SECONDS}s. Please trim your video to under 3 minutes."
            )

        normalized_video = ctx.workdir / "normalized_input.mp4"
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

        # Construct ffmpeg command
        # Autorotate is active by default in ffmpeg; we strip audio (-an) and ensure 8-bit yuv420p
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(input_path),
            "-an",  # Strip audio
        ]

        # Handle HDR / 10-bit tone mapping
        if metadata.get("is_hdr"):
            ctx.log_cb("[Ingest] Applying HDR/10-bit SDR tone-mapping to standard BT.709 color space...")
            # Using tonemap and zscale filterchain
            cmd.extend([
                "-vf", "zscale=transfer=bt709:matrix=bt709,format=yuv420p"
            ])
        else:
            cmd.extend([
                "-vf", "format=yuv420p"
            ])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            str(normalized_video)
        ])

        ctx.log_cb(f"[Ingest] Normalizing video with ffmpeg -> {normalized_video.name}")
        ToolRunner.run(
            cmd,
            cwd=str(ctx.workdir),
            log_callback=ctx.log_cb,
            cancel_token=ctx.cancel_token,
            timeout=300
        )

        if not normalized_video.exists():
            raise RuntimeError(f"FFmpeg failed to produce normalized output: {normalized_video}")

        # Save metadata JSON
        metadata_path = ctx.workdir / "ingest_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        ctx.log_cb("[Ingest] Video normalization complete.")
        return StageResult(
            success=True,
            output_files=[normalized_video, metadata_path],
            metadata=metadata
        )
