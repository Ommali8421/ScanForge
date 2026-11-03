"""
Scale-Invariant Mesh Route Classifier (Milestone P4)
Automatically selects between Photogrammetry (Route A) and Depth Fusion (Route B)
based on scale-invariant visual texture variance and SIFT track density:
  - Mean Laplacian texture variance < 120.0 -> Route B
  - SIFT 3D tracks per registered frame < 800 -> Route B
  - Else -> Route A
Emits mesh_route_decision.json with decision, metrics, and human-readable explanation.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import cv2
import numpy as np

from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.depth.depth_align import parse_colmap_sparse, find_colmap_sparse_dir
from app.utils.logging import logger


class RouteClassifierStage(Stage):
    """
    Evaluates keyframe visual texture and SIFT 3D track density to classify
    whether Route A (Photogrammetry OpenMVS) or Route B (Depth Fusion TSDF) is optimal.
    """
    name: str = "route_classifier"
    weight: float = 0.5
    declared_outputs: List[str] = ["mesh_route_decision.json"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[RouteClassifier] Evaluating scale-invariant heuristics for mesh route selection...")

        user_override = ctx.params.get("options", {}).get("mesh_route", "auto").lower()

        frames_dir = ctx.workdir / "frames"
        all_frames = sorted(list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("*.png"))) if frames_dir.exists() else []

        # Sample up to 20 keyframes across the sequence
        sample_frames = []
        if all_frames:
            step = max(1, len(all_frames) // 20)
            sample_frames = all_frames[::step][:20]

        variances = []
        for f_path in sample_frames:
            img = cv2.imread(str(f_path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                # Downscale to standard 720p resolution for scale-invariant Laplacian
                if img.shape[0] > 720:
                    scale = 720.0 / img.shape[0]
                    img = cv2.resize(img, (int(img.shape[1] * scale), 720), interpolation=cv2.INTER_AREA)
                lap_var = float(cv2.Laplacian(img, cv2.CV_64F).var())
                variances.append(lap_var)

        mean_variance = float(np.mean(variances)) if variances else 150.0

        # Sparse 3D points and track density from COLMAP
        sparse_dir = find_colmap_sparse_dir(ctx.workdir)
        total_points = 0
        total_images = 1
        tracks_per_image = 1000.0

        if sparse_dir.exists():
            try:
                cams, images, points3d = parse_colmap_sparse(sparse_dir)
                total_points = len(points3d)
                total_images = max(len(images), 1)
                tracks_per_image = float(total_points / total_images)
            except Exception as e:
                logger.warning(f"[RouteClassifier] Error parsing sparse model: {e}")

        # Classification decision
        is_textureless = mean_variance < 120.0
        is_sparse_features = tracks_per_image < 800.0

        if user_override == "depth_fusion":
            chosen_route = "depth_fusion"
            explanation = f"User override requested Depth Fusion (Route B). (Texture variance: {mean_variance:.1f}, Tracks/frame: {tracks_per_image:.1f})."
        elif user_override in {"photogrammetry", "openmvs"}:
            chosen_route = "photogrammetry"
            explanation = f"User override requested Photogrammetry (Route A). (Texture variance: {mean_variance:.1f}, Tracks/frame: {tracks_per_image:.1f})."
        else:
            # Auto heuristic
            if is_textureless or is_sparse_features:
                chosen_route = "depth_fusion"
                reasons = []
                if is_textureless:
                    reasons.append(f"low texture variance ({mean_variance:.1f} < 120.0)")
                if is_sparse_features:
                    reasons.append(f"low SIFT track density ({tracks_per_image:.1f} < 800 tracks/frame)")
                explanation = f"Auto selected Depth Fusion (Route B) due to {' and '.join(reasons)}. Depth-fusion TSDF prevents planar wall and floor holes."
            else:
                chosen_route = "photogrammetry"
                explanation = f"Auto selected Photogrammetry (Route A) due to high texture variance ({mean_variance:.1f} >= 120.0) and rich SIFT track density ({tracks_per_image:.1f} >= 800). OpenMVS provides maximum edge sharpness."

        ctx.log_cb(f"[RouteClassifier] Decision: '{chosen_route.upper()}'. Reason: {explanation}")

        decision_data = {
            "decision": chosen_route,
            "requested_route": user_override,
            "mean_laplacian_variance": round(mean_variance, 2),
            "tracks_per_image": round(tracks_per_image, 1),
            "total_sparse_points": total_points,
            "registered_images": total_images,
            "is_textureless": is_textureless,
            "is_sparse_features": is_sparse_features,
            "explanation": explanation,
        }

        decision_file = ctx.workdir / "mesh_route_decision.json"
        decision_file.write_text(json.dumps(decision_data, indent=2))

        return StageResult(
            success=True,
            output_files=[decision_file],
            metadata=decision_data
        )
