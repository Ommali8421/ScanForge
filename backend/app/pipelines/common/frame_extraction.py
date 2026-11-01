"""
Real Frame Extraction Stage
Performs adaptive video sampling, variance-of-Laplacian sharpness scoring,
inter-frame optical flow analysis for fast rotation and rotation-in-place detection,
deduplication, and quality warning generation.

Optimized for long video sequences (several minutes) via two-pass zero-RAM streaming:
- Pass 1: Streams video frames without retaining raw image arrays in RAM, extracting
  only 320x180 thumbnails and sharpness scores.
- Adaptive keyframe budget curve: Dynamically bounds target keyframes based on duration
  and quality preset (Draft: 180, Standard: 300, High: 380) to respect the 8 GB VRAM budget.
- Pass 2: Sequential retrieval using cap.grab() for skipped frames and cap.retrieve()
  ONLY for selected keyframe indices. Zero seeking, zero redundant decoding.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np
from app.pipelines.base import Stage, JobContext, StageResult


def compute_adaptive_keyframe_budget(
    duration: float,
    quality: str = "standard",
    max_frames_override: Optional[int] = None
) -> Tuple[int, float]:
    """
    Computes adaptive target keyframe count and effective target fps based on duration
    and quality tier to respect 8 GB VRAM budget while ensuring thorough room coverage.

    Diminishing returns curve:
    - T <= 30s: N = min(120, round(T * 3.3))
    - 30s < T <= 90s: N = min(200, 100 + round((T - 30) * 1.6))
    - 90s < T <= 180s: N = min(280, 200 + round((T - 90) * 0.8))
    - T > 180s: N = min(max_budget, 280 + round((T - 180) * 0.2))
    """
    quality_lower = (quality or "standard").lower()
    if quality_lower == "draft":
        max_budget = 180
    elif quality_lower == "high":
        max_budget = 380
    else:
        max_budget = 300

    if max_frames_override is not None:
        max_budget = int(max_frames_override)

    if duration <= 30.0:
        n = min(120, round(duration * 3.3))
    elif duration <= 90.0:
        n = min(200, 100 + round((duration - 30.0) * 1.6))
    elif duration <= 180.0:
        n = min(280, 200 + round((duration - 90.0) * 0.8))
    else:
        n = min(max_budget, 280 + round((duration - 180.0) * 0.2))

    target_frames = max(40, min(max_budget, int(n)))
    effective_fps = target_frames / duration if duration > 0 else 3.3
    return target_frames, effective_fps


class FrameExtractionStage(Stage):
    name: str = "frame_extraction"
    weight: float = 2.0
    declared_outputs: List[str] = ["frames", "frame_extraction_report.json"]

    def _analyze_motion_and_homography(
        self, prev_gray_small: np.ndarray, curr_gray_small: np.ndarray
    ) -> Tuple[bool, bool, float]:
        """
        Analyze motion between two consecutive downsampled frames:
        1. Fast rotation: high flow magnitude and mostly uniform flow direction.
        2. Rotation-in-place: flow well-explained by a single homography (no parallax).
        Returns (is_fast_rotation, is_rotation_in_place, mean_flow_magnitude).
        """
        # Dense optical flow via Farneback
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray_small,
            curr_gray_small,
            None,
            pyr_scale=0.5,
            levels=2,
            winsize=13,
            iterations=2,
            poly_n=5,
            poly_sigma=1.1,
            flags=0
        )
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mean_mag = float(np.mean(mag))
        ang_std = float(np.std(ang))

        # Fast rotation heuristic: high flow magnitude with uniform angle
        is_fast_rotation = (mean_mag > 12.0 and ang_std < 0.65)

        # Rotation-in-place heuristic: check if flow corresponds to single homography
        # Sample points on a regular grid
        h, w = prev_gray_small.shape
        step = 16
        y_indices, x_indices = np.mgrid[step:h-step:step, step:w-step:step]
        pts_prev = np.column_stack((x_indices.ravel(), y_indices.ravel())).astype(np.float32)

        # Predicted points based on flow
        flow_samples = flow[y_indices.ravel(), x_indices.ravel()]
        pts_curr = pts_prev + flow_samples

        is_rotation_in_place = False
        if len(pts_prev) >= 8 and mean_mag > 1.5:
            _, inlier_mask = cv2.findHomography(pts_prev, pts_curr, cv2.RANSAC, 2.5)
            if inlier_mask is not None:
                inlier_ratio = float(np.sum(inlier_mask)) / float(len(inlier_mask))
                # If >= 92% of flow vectors fit a single planar homography with noticeable motion
                if inlier_ratio >= 0.92 and mean_mag < 25.0:
                    is_rotation_in_place = True

        return is_fast_rotation, is_rotation_in_place, mean_mag

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[FrameExtraction] Starting adaptive frame extraction and quality analysis...")
        video_path = ctx.workdir / "normalized_input.mp4"
        if not video_path.exists():
            # Fallback to finding video if normalized_input is missing
            matches = list(ctx.workdir.glob("*.mp4"))
            if not matches:
                raise FileNotFoundError("Video file not found in workdir for frame extraction.")
            video_path = matches[0]

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {video_path}")

        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        duration = total_video_frames / video_fps if video_fps > 0 else 30.0

        options = ctx.params.get("options", {})
        quality = ctx.params.get("quality", "standard")
        uniform_sampling = bool(options.get("uniform_sampling", False))

        # Compute adaptive keyframe budget based on duration and quality preset
        max_override = options.get("max_frames")
        if max_override is not None:
            max_override = int(max_override)
        target_frames, effective_target_fps = compute_adaptive_keyframe_budget(
            duration=duration,
            quality=quality,
            max_frames_override=max_override
        )

        frames_dir = ctx.workdir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        if uniform_sampling:
            sample_step = video_fps / effective_target_fps if effective_target_fps > 0 else 1.0
            target_indices = [int(round(i * sample_step)) for i in range(target_frames) if int(round(i * sample_step)) < total_video_frames]
            ctx.log_cb(f"[FrameExtraction] Uniform sampling enabled: extracting {len(target_indices)} frames at {effective_target_fps:.1f} fps.")
            target_set = set(target_indices)

            # Pass 2 streaming with cap.grab() and cap.retrieve()
            curr_idx = 0
            saved_count = 0
            while True:
                if ctx.cancel_token.is_cancelled():
                    cap.release()
                    raise RuntimeError("Frame extraction cancelled by user.")
                if not cap.grab():
                    break
                if curr_idx in target_set:
                    ret, frame = cap.retrieve()
                    if ret:
                        out_path = frames_dir / f"frame_{saved_count:04d}.jpg"
                        cv2.imwrite(str(out_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                        saved_count += 1
                curr_idx += 1
            cap.release()

            ctx.log_cb(f"[FrameExtraction] Uniform extraction complete: saved {saved_count} frames.")
            report = {
                "total_video_frames": total_video_frames,
                "video_fps": round(video_fps, 2),
                "duration_seconds": round(duration, 2),
                "sampling_mode": "uniform",
                "target_fps": round(effective_target_fps, 2),
                "extracted_frames": saved_count
            }
            report_path = ctx.workdir / "frame_extraction_report.json"
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)
            return StageResult(
                success=True,
                output_files=[frames_dir, report_path],
                metadata=report
            )

        # Candidate sampling interval at 2x rate for adaptive windowing
        candidate_interval = max(1, int(round(video_fps / (effective_target_fps * 2.0))))

        ctx.log_cb(
            f"[FrameExtraction] Video: {total_video_frames} frames ({duration:.1f}s @ {video_fps:.1f} fps). "
            f"Quality='{quality}' -> Target frames: {target_frames} (~{effective_target_fps:.2f} fps), "
            f"Candidate interval: every {candidate_interval} frames."
        )

        # -------------------------------------------------------------
        # Pass 1: Streaming Candidate Evaluation (Zero full-frame RAM retention)
        # -------------------------------------------------------------
        candidates: List[Dict[str, Any]] = []
        frame_idx = 0
        quality_warnings: List[str] = []

        while True:
            if ctx.cancel_token.is_cancelled():
                cap.release()
                raise RuntimeError("Frame extraction cancelled by user.")

            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % candidate_interval == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # Sharpness via variance of Laplacian
                sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                # Downscaled thumbnail for optical flow analysis (320x180 = 57 KB)
                small_gray = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)

                # Store ONLY metadata and small thumbnail (never full-resolution frame)
                candidates.append({
                    "frame_idx": frame_idx,
                    "timestamp": frame_idx / video_fps,
                    "gray_small": small_gray,
                    "sharpness": sharpness
                })

            frame_idx += 1

        cap.release()
        ctx.log_cb(f"[FrameExtraction] Pass 1 complete: evaluated {len(candidates)} candidate frames in streaming mode.")

        if not candidates:
            raise RuntimeError("No candidate frames could be extracted from video.")

        # Compute sharpness threshold (adaptive: 15th percentile or 25.0)
        all_sharpness = [c["sharpness"] for c in candidates]
        sharpness_threshold = max(25.0, float(np.percentile(all_sharpness, 15)))

        # Group candidates into time windows and select the best (sharpest) non-blurry candidate
        window_size_sec = duration / target_frames if target_frames > 0 else 0.3
        windows: Dict[int, List[Dict[str, Any]]] = {}

        for c in candidates:
            win_id = int(c["timestamp"] / window_size_sec)
            windows.setdefault(win_id, []).append(c)

        kept_candidates: List[Dict[str, Any]] = []
        dropped_blur_count = 0
        dropped_duplicate_count = 0
        dropped_fast_motion_count = 0
        rotation_in_place_warnings = 0

        prev_selected: Optional[Dict[str, Any]] = None

        # Sort windows by ID
        for win_id in sorted(windows.keys()):
            win_cands = windows[win_id]
            # Sort candidates in this window by sharpness descending
            win_cands.sort(key=lambda x: x["sharpness"], reverse=True)

            selected_cand = None
            for cand in win_cands:
                if cand["sharpness"] < sharpness_threshold:
                    dropped_blur_count += 1
                    continue

                if prev_selected is not None:
                    # Analyze motion with previous selected frame
                    is_fast_rot, is_rot_in_place, mean_mag = self._analyze_motion_and_homography(
                        prev_selected["gray_small"], cand["gray_small"]
                    )

                    if mean_mag < 0.6:
                        # Near-stationary / duplicate
                        dropped_duplicate_count += 1
                        continue

                    if is_fast_rot:
                        # Too blurry / fast rotational swing
                        dropped_fast_motion_count += 1
                        continue

                    if is_rot_in_place:
                        rotation_in_place_warnings += 1

                selected_cand = cand
                break

            # If all candidates in window were below threshold, take the sharpest if window is empty
            if selected_cand is None and win_cands:
                best = win_cands[0]
                if prev_selected is None or cv2.norm(best["gray_small"], prev_selected["gray_small"], cv2.NORM_L1) > 100:
                    selected_cand = best

            if selected_cand is not None:
                kept_candidates.append(selected_cand)
                prev_selected = selected_cand

        # If too few frames kept, fallback to top-N sharpest candidates uniformly spaced
        if len(kept_candidates) < 40:
            ctx.log_cb("[FrameExtraction] Notice: Adaptive windowing selected few frames. Supplementing with sharpest frames.")
            step = max(1, len(candidates) // target_frames)
            kept_candidates = [candidates[i] for i in range(0, len(candidates), step)]

        # Map frame indices for Pass 2 streaming retrieval
        # Sort by frame_idx to ensure monotonic sequential decoding
        kept_candidates.sort(key=lambda x: x["frame_idx"])
        kept_indices = {c["frame_idx"] for c in kept_candidates}

        # -------------------------------------------------------------
        # Pass 2: Sequential Targeted Frame Writing using cap.grab() / cap.retrieve()
        # -------------------------------------------------------------
        ctx.log_cb(f"[FrameExtraction] Pass 2: Streaming and writing {len(kept_candidates)} selected frames to {frames_dir.name}...")
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Could not reopen video file for Pass 2: {video_path}")

        curr_idx = 0
        saved_count = 0
        while True:
            if ctx.cancel_token.is_cancelled():
                cap.release()
                raise RuntimeError("Frame extraction cancelled by user.")

            # Fast grab (only demuxes packet header, skips full color decoding for skipped frames)
            if not cap.grab():
                break

            if curr_idx in kept_indices:
                ret, frame = cap.retrieve()
                if ret:
                    frame_filename = frames_dir / f"frame_{saved_count:04d}.jpg"
                    cv2.imwrite(str(frame_filename), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                    saved_count += 1

            curr_idx += 1

        cap.release()
        ctx.log_cb(f"[FrameExtraction] Pass 2 complete: successfully saved {saved_count} frames to disk.")

        # Generate warnings
        if dropped_blur_count > len(candidates) * 0.35:
            quality_warnings.append(
                f"High motion blur: {dropped_blur_count} candidate frames had low sharpness. Consider moving slower."
            )
        if dropped_fast_motion_count > 5:
            quality_warnings.append(
                f"Fast camera rotation detected ({dropped_fast_motion_count} sections dropped). Smooth translation produces better meshes."
            )
        if rotation_in_place_warnings > 5:
            quality_warnings.append(
                "Rotation-in-place detected (panning without translation). Walk through the space with parallax for best 3D reconstruction."
            )

        mean_kept_sharpness = float(np.mean([c["sharpness"] for c in kept_candidates])) if kept_candidates else 0.0

        report = {
            "total_video_frames": total_video_frames,
            "candidate_frames_evaluated": len(candidates),
            "frames_kept": saved_count,
            "frames_dropped_blur": dropped_blur_count,
            "frames_dropped_duplicate": dropped_duplicate_count,
            "frames_dropped_fast_motion": dropped_fast_motion_count,
            "mean_sharpness": round(mean_kept_sharpness, 1),
            "sharpness_threshold": round(sharpness_threshold, 1),
            "quality_warnings": quality_warnings
        }

        report_path = ctx.workdir / "frame_extraction_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        ctx.log_cb(
            f"[FrameExtraction] Complete: {saved_count} frames kept (mean sharpness: {mean_kept_sharpness:.1f}). "
            f"Dropped: {dropped_blur_count} blur, {dropped_duplicate_count} dup, {dropped_fast_motion_count} fast rot."
        )
        if quality_warnings:
            for w in quality_warnings:
                ctx.log_cb(f"[FrameExtraction Warning] {w}")

        return StageResult(
            success=True,
            output_files=[frames_dir, report_path],
            metadata=report
        )
