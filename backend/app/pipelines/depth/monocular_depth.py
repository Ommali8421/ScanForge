"""
Monocular Depth Estimation Stage (Milestone P4 Route B)
Runs Depth Anything V2 Small (Apache-2.0, ~95 MB) across video frames to predict
dense affine-invariant inverse-depth (disparity) maps.
Adheres to 8 GB VRAM budget by processing frames in lightweight batches with GPU cache clearing.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
import cv2
import numpy as np

from app.config import settings
from app.pipelines.base import Stage, JobContext, StageResult
from app.utils.logging import logger


class MonocularDepthStage(Stage):
    """
    Predicts affine-invariant inverse depth (disparity) for each video frame
    using Depth Anything V2 Small (Apache-2.0).
    """
    name: str = "monocular_depth"
    weight: float = 3.0
    declared_outputs: List[str] = ["depth_raw"]

    def run(self, ctx: JobContext) -> StageResult:
        # Skip for Route A (photogrammetry) — OpenMVS provides the mesh directly
        decision_file = ctx.workdir / "mesh_route_decision.json"
        if decision_file.exists():
            try:
                dec = json.loads(decision_file.read_text()).get("decision", "")
                if dec == "photogrammetry":
                    ctx.log_cb("[MonocularDepth] Route A (Photogrammetry) active. Skipping monocular depth inference.")
                    return StageResult(success=True, skipped_cache=True)
            except Exception:
                pass

        ctx.log_cb("[MonocularDepth] Initializing Depth Anything V2 Small inference...")
        depth_out_dir = ctx.workdir / "depth_raw"
        depth_out_dir.mkdir(parents=True, exist_ok=True)

        frames_dir = ctx.workdir / "frames"
        if not frames_dir.exists():
            raise FileNotFoundError(f"[MonocularDepth] Frames directory not found: {frames_dir}")

        # Prioritize frames that are registered in COLMAP sparse model
        registered_names: List[str] = []
        sparse_images = ctx.workdir / "sparse" / "0" / "images.txt"
        if not sparse_images.exists():
            sparse_images = ctx.workdir / "aligned_sparse" / "0" / "images.txt"

        if sparse_images.exists():
            for line in sparse_images.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 10 and any(parts[9].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
                    registered_names.append(parts[9])

        if registered_names:
            frame_files = [frames_dir / name for name in registered_names if (frames_dir / name).exists()]
            ctx.log_cb(f"[MonocularDepth] Found {len(frame_files)} registered COLMAP keyframes.")
        else:
            frame_files = sorted(list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("*.png")))
            ctx.log_cb(f"[MonocularDepth] Found {len(frame_files)} extracted video frames.")

        if not frame_files:
            raise FileNotFoundError("[MonocularDepth] No image frames found to process.")

        is_mock = (settings.SCANFORGE_ENGINE == "mock") or (ctx.params.get("options", {}).get("engine") == "mock")

        if is_mock:
            ctx.log_cb("[MonocularDepth] MOCK engine active: generating synthetic disparity maps...")
            for idx, f_path in enumerate(frame_files):
                img = cv2.imread(str(f_path))
                h, w = (img.shape[0], img.shape[1]) if img is not None else (720, 1280)
                # Synthetic gradient disparity (higher disparity = closer floor, lower = distant ceiling)
                y_coords, x_coords = np.mgrid[0:h, 0:w]
                disp = 0.5 + 0.4 * (y_coords / float(h))
                out_npy = depth_out_dir / f"{f_path.stem}.npy"
                np.save(str(out_npy), disp.astype(np.float32))

            return StageResult(
                success=True,
                output_files=[depth_out_dir],
                metadata={"total_frames": len(frame_files), "engine": "mock"}
            )

        # Real GPU Inference with Depth Anything V2 Small
        import torch
        try:
            from app.pipelines.depth.depth_anything_v2.dpt import DepthAnythingV2
        except ImportError:
            import sys
            if "/data/models/depth_anything_v2" not in sys.path:
                sys.path.insert(0, "/data/models/depth_anything_v2")
            from depth_anything_v2.dpt import DepthAnythingV2

        device = "cuda" if torch.cuda.is_available() else "cpu"
        ckpt_path = Path("/data/models/depth_anything_v2/depth_anything_v2_vits.pth")
        if not ckpt_path.exists():
            raise FileNotFoundError(
                f"[MonocularDepth] Checkpoint not found at {ckpt_path}. "
                "Ensure depth_anything_v2_vits.pth is downloaded in /data/models/depth_anything_v2/."
            )

        ctx.log_cb(f"[MonocularDepth] Loading Depth Anything V2 Small ({ckpt_path.stat().st_size / 1024**2:.1f} MB) on {device}...")
        model_configs = {
            "vits": {"encoder": "vits", "features": 64, "out_channels": [48, 96, 192, 384]},
        }
        model = DepthAnythingV2(**model_configs["vits"])
        sd = torch.load(str(ckpt_path), map_location="cpu", weights_only=True)
        model.load_state_dict(sd)
        model = model.to(device).eval()

        t0 = time.time()
        num_frames = len(frame_files)
        ctx.log_cb(f"[MonocularDepth] Processing {num_frames} frames on {device}...")

        with torch.no_grad():
            for idx, f_path in enumerate(frame_files):
                raw_bgr = cv2.imread(str(f_path))
                if raw_bgr is None:
                    continue

                # Run inference; returns 2D numpy array of inverse depth (disparity)
                disp = model.infer_image(raw_bgr)
                out_npy = depth_out_dir / f"{f_path.stem}.npy"
                np.save(str(out_npy), disp.astype(np.float32))

                if (idx + 1) % 25 == 0 or (idx + 1) == num_frames:
                    elapsed = time.time() - t0
                    fps = (idx + 1) / max(elapsed, 1e-3)
                    ctx.log_cb(f"[MonocularDepth] Processed {idx+1}/{num_frames} frames ({fps:.1f} fps)...")

        # Cleanup GPU memory immediately
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        total_time = time.time() - t0
        ctx.log_cb(f"[MonocularDepth] Completed monocular depth estimation in {total_time:.1f}s ({num_frames/max(total_time, 1e-3):.1f} fps).")

        return StageResult(
            success=True,
            output_files=[depth_out_dir],
            metadata={
                "total_frames": num_frames,
                "duration_seconds": round(total_time, 2),
                "device": device
            }
        )

