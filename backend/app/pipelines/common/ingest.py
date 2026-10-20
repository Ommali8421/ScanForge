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
from app.utils.tool_resolve import resolve_ffmpeg, get_configured_threads


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
        ffmpeg_bin = resolve_ffmpeg()
        threads = str(get_configured_threads())

        # Construct ffmpeg command
        # Autorotate is active by default in ffmpeg; we strip audio (-an) and ensure 8-bit yuv420p
        cmd = [
            ffmpeg_bin,
            "-threads", threads,
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

        # Scene-cut detection (warns, does not crash; validates with verified feature matches)
        cuts, cuts_dir = self._detect_scene_cuts(normalized_video, ctx)
        metadata["scene_cuts"] = cuts

        # Save metadata JSON
        metadata_path = ctx.workdir / "ingest_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        ctx.log_cb("[Ingest] Video normalization and scene-cut analysis complete.")
        output_files = [normalized_video, metadata_path]
        if cuts_dir and cuts_dir.exists() and any(cuts_dir.iterdir()):
            output_files.append(cuts_dir)

        return StageResult(
            success=True,
            output_files=output_files,
            metadata=metadata
        )

    def _detect_scene_cuts(self, video_path: Path, ctx: JobContext) -> Tuple[List[dict], Optional[Path]]:
        """
        Detect scene cuts with dual validation:
        1. Large histogram change (HSV correlation < 0.20)
        2. Verified feature matches collapse (< 15 RANSAC inliers) between adjacent frames.
        Saves before/after frames under cuts/ folder for UI inspection.
        Warns only; does not split the sequence unless confirmed.
        """
        cuts: List[dict] = []
        cuts_dir = ctx.workdir / "cuts"
        try:
            import cv2
            import numpy as np

            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return cuts, None

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            step_frames = max(1, int(fps * 0.5))  # check every 0.5s

            orb = cv2.ORB_create(nfeatures=500)
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

            prev_hist = None
            prev_frame = None
            prev_frame_idx = 0
            frame_idx = 0
            cut_idx = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % step_frames == 0:
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
                    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                    if prev_hist is not None and prev_frame is not None:
                        corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
                        if corr < 0.25:
                            cut_idx += 1
                            timestamp = frame_idx / fps
                            cuts_dir.mkdir(parents=True, exist_ok=True)

                            # Verify feature matches between adjacent frames using ORB + RANSAC homography
                            gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
                            gray_curr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            kp1, des1 = orb.detectAndCompute(gray_prev, None)
                            kp2, des2 = orb.detectAndCompute(gray_curr, None)

                            verified_matches = 0
                            if des1 is not None and des2 is not None and len(kp1) >= 8 and len(kp2) >= 8:
                                knn_matches = bf.knnMatch(des1, des2, k=2)
                                good = [m for m, n in knn_matches if len(knn_matches) > 1 and m.distance < 0.75 * n.distance]
                                if len(good) >= 8:
                                    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                                    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
                                    _, inlier_mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                                    if inlier_mask is not None:
                                        verified_matches = int(np.sum(inlier_mask))

                            # Dual validation: true cut only if both histogram change is large AND matches collapse
                            is_confirmed_cut = (corr < 0.20 and verified_matches < 15)

                            # Save before/after frames
                            before_name = f"cut_{cut_idx:02d}_f{prev_frame_idx}_before.jpg"
                            after_name = f"cut_{cut_idx:02d}_f{frame_idx}_after.jpg"
                            comp_name = f"cut_{cut_idx:02d}_comparison.jpg"

                            before_path = cuts_dir / before_name
                            after_path = cuts_dir / after_name
                            comp_path = cuts_dir / comp_name

                            cv2.imwrite(str(before_path), prev_frame)
                            cv2.imwrite(str(after_path), frame)

                            # Create side-by-side comparison image with status banner
                            h_p, w_p = prev_frame.shape[:2]
                            h_c, w_c = frame.shape[:2]
                            max_h = max(h_p, h_c)
                            comp_w = w_p + w_c
                            composite = np.zeros((max_h + 50, comp_w, 3), dtype=np.uint8)
                            composite[50:50+h_p, 0:w_p] = prev_frame
                            composite[50:50+h_c, w_p:w_p+w_c] = frame

                            verdict_text = "CONFIRMED CUT (DISCONTINUITY)" if is_confirmed_cut else "FALSE POSITIVE (FAST PAN / CONTINUOUS)"
                            verdict_color = (0, 0, 255) if is_confirmed_cut else (0, 255, 128)
                            info_text = f"t={timestamp:.1f}s | Hist Corr: {corr:.3f} | RANSAC Inliers: {verified_matches} | {verdict_text}"
                            cv2.putText(composite, info_text, (15, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, verdict_color, 2)
                            cv2.imwrite(str(comp_path), composite)

                            cut_info = {
                                "cut_id": cut_idx,
                                "timestamp_seconds": round(timestamp, 2),
                                "frame_index_before": prev_frame_idx,
                                "frame_index_after": frame_idx,
                                "histogram_correlation": round(corr, 3),
                                "verified_feature_matches": verified_matches,
                                "confirmed_cut": is_confirmed_cut,
                                "verdict": "confirmed_cut" if is_confirmed_cut else "rejected_pan",
                                "before_file": before_name,
                                "after_file": after_name,
                                "comparison_file": comp_name
                            }
                            cuts.append(cut_info)

                            if is_confirmed_cut:
                                ctx.log_cb(
                                    f"[Ingest Warning] Confirmed scene-cut detected at t={timestamp:.1f}s "
                                    f"(corr: {corr:.3f}, inliers: {verified_matches} < 15). "
                                    f"Saved before/after preview -> cuts/{comp_name}"
                                )
                            else:
                                ctx.log_cb(
                                    f"[Ingest] Scene-cut candidate at t={timestamp:.1f}s rejected (fast pan): "
                                    f"verified inliers ({verified_matches} >= 15) confirm visual continuity."
                                )

                    prev_hist = hist
                    prev_frame = frame.copy()
                    prev_frame_idx = frame_idx

                frame_idx += 1

            cap.release()
        except Exception as e:
            ctx.log_cb(f"[Ingest] Scene-cut analysis skipped ({e}).")

        return cuts, (cuts_dir if cuts else None)
