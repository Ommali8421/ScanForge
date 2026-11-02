"""
Interior Floater Cleanup Stage for 3D Gaussian Splatting
Prunes mist, giant floaters, spatial statistical outliers, and exterior envelope floaters.
Outputs cleaned_splat.ply.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
from scipy.spatial import cKDTree
from plyfile import PlyData, PlyElement

from app.pipelines.base import Stage, StageResult, JobContext
from app.utils.logging import logger


class SplatCleanupStage(Stage):
    """
    Cleans raw 3DGS PLY point cloud:
    a) Opacity mist pruning (alpha < 0.05)
    b) Giant floater scale pruning (s_max > 3.0 * median or > 0.5m)
    c) Spatial Statistical Outlier Removal (KDTree SOR: k=20, std_ratio=2.0)
    d) Camera-trajectory + room-plane envelope clipping
    """
    name: str = "splat_cleanup"
    weight: float = 1.0
    declared_outputs: List[str] = [
        "cleaned_splat.ply",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[SplatCleanup] Starting interior floater cleanup and outlier removal...")
        t0 = time.time()

        input_ply = ctx.workdir / "splat.ply"
        if not input_ply.exists():
            raise FileNotFoundError(f"[SplatCleanup] Raw splat PLY missing at {input_ply}")

        # Read input PLY
        plydata = PlyData.read(str(input_ply))
        vertex = plydata["vertex"].data
        num_raw = len(vertex)
        ctx.log_cb(f"[SplatCleanup] Loaded raw splat model with {num_raw:,} Gaussians.")

        if num_raw == 0:
            raise ValueError("[SplatCleanup] Raw splat model has 0 Gaussians")

        x = np.asarray(vertex["x"], dtype=np.float32)
        y = np.asarray(vertex["y"], dtype=np.float32)
        z = np.asarray(vertex["z"], dtype=np.float32)

        opacity_raw = np.asarray(vertex["opacity"], dtype=np.float32)
        s0 = np.asarray(vertex["scale_0"], dtype=np.float32)
        s1 = np.asarray(vertex["scale_1"], dtype=np.float32)
        s2 = np.asarray(vertex["scale_2"], dtype=np.float32)

        # 1. Opacity mist pruning (alpha < 0.05)
        # Convert raw logit opacity to linear alpha: sigmoid(opacity)
        alpha = 1.0 / (1.0 + np.exp(-np.clip(opacity_raw, -20.0, 20.0)))
        mask_opacity = alpha >= 0.05
        ctx.log_cb(
            f"[SplatCleanup] Opacity mist filter: retained {np.sum(mask_opacity):,}/{num_raw:,} "
            f"({np.sum(mask_opacity)/num_raw*100:.1f}%), dropped {num_raw - np.sum(mask_opacity):,} mist Gaussians (alpha < 0.05)."
        )

        # 2. Giant floater scale pruning (s_max > 3.0 * median or > 0.5m)
        # Convert raw log scale to linear scale: exp(scale)
        scale_linear_0 = np.exp(np.clip(s0, -20.0, 5.0))
        scale_linear_1 = np.exp(np.clip(s1, -20.0, 5.0))
        scale_linear_2 = np.exp(np.clip(s2, -20.0, 5.0))
        s_max = np.maximum(scale_linear_0, np.maximum(scale_linear_1, scale_linear_2))

        valid_scales = s_max[mask_opacity] if np.any(mask_opacity) else s_max
        median_scale = float(np.median(valid_scales)) if len(valid_scales) > 0 else 0.05
        scale_threshold = min(3.0 * median_scale, 0.50)

        mask_scale = s_max <= scale_threshold
        mask_cand = mask_opacity & mask_scale
        ctx.log_cb(
            f"[SplatCleanup] Giant floater filter (median scale={median_scale:.4f}m, max cutoff={scale_threshold:.4f}m): "
            f"retained {np.sum(mask_cand):,}/{num_raw:,} ({np.sum(mask_cand)/num_raw*100:.1f}%)."
        )

        # 3. Spatial Statistical Outlier Removal (KDTree SOR: k=20, std_ratio=2.0)
        cand_indices = np.where(mask_cand)[0]
        if len(cand_indices) > 50:
            coords_cand = np.column_stack([x[cand_indices], y[cand_indices], z[cand_indices]])
            tree = cKDTree(coords_cand)
            k_val = min(20, len(coords_cand))
            dists, _ = tree.query(coords_cand, k=k_val, workers=2)
            # Skip first column (distance to self = 0.0)
            neighbor_dists = dists[:, 1:] if dists.shape[1] > 1 else dists
            mean_dist = np.mean(neighbor_dists, axis=1)

            dist_mean = float(np.mean(mean_dist))
            dist_std = float(np.std(mean_dist))
            sor_cutoff = dist_mean + 2.0 * dist_std

            mask_sor_local = mean_dist <= sor_cutoff
            sor_retained_indices = cand_indices[mask_sor_local]
            ctx.log_cb(
                f"[SplatCleanup] Spatial SOR filter (mean dist={dist_mean:.3f}m, std={dist_std:.3f}m, cutoff={sor_cutoff:.3f}m): "
                f"retained {len(sor_retained_indices):,}/{len(cand_indices):,}."
            )
        else:
            sor_retained_indices = cand_indices

        # 4. Camera-trajectory + room-plane envelope clipping
        # Read pre_align_metadata or room_analysis to obtain room bounds
        meta_file = ctx.workdir / "pre_align_metadata.json"
        analysis_file = ctx.workdir / "room_analysis.json"

        # Read aligned camera positions from aligned_sparse/0/images.txt
        aligned_images_txt = ctx.workdir / "aligned_sparse" / "0" / "images.txt"
        cam_positions = []
        if aligned_images_txt.exists():
            from scipy.spatial.transform import Rotation as R
            with open(aligned_images_txt, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 10 and any(parts[9].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
                        qw, qx, qy, qz = map(float, parts[1:5])
                        tx, ty, tz = map(float, parts[5:8])
                        rot = R.from_quat([qx, qy, qz, qw]).as_matrix()
                        t_vec = np.array([tx, ty, tz])
                        cam_pos = -rot.T @ t_vec
                        cam_positions.append(cam_pos)

        if cam_positions:
            cams = np.array(cam_positions)
            cam_min = np.min(cams, axis=0)
            cam_max = np.max(cams, axis=0)
            cam_span = cam_max - cam_min

            # Horizontal margin: expand by max(1.5 * span, 2.5m)
            x_margin = max(1.5 * cam_span[0], 2.5)
            z_margin = max(1.5 * cam_span[2], 2.5)

            # Vertical clearance: floor is at Y=0.0, allow small subfloor margin -0.25m
            y_min = -0.25
            y_max = max(cam_max[1] + 1.8, 4.0)

            x_min = cam_min[0] - x_margin
            x_max = cam_max[0] + x_margin
            z_min = cam_min[2] - z_margin
            z_max = cam_max[2] + z_margin
        else:
            # Fallback bounds from coordinate spread
            x_min, x_max = -20.0, 20.0
            y_min, y_max = -0.25, 8.0
            z_min, z_max = -20.0, 20.0

        ctx.log_cb(
            f"[SplatCleanup] Room envelope bounds: X=[{x_min:.2f}, {x_max:.2f}], "
            f"Y=[{y_min:.2f}, {y_max:.2f}], Z=[{z_min:.2f}, {z_max:.2f}]."
        )

        cand_x = x[sor_retained_indices]
        cand_y = y[sor_retained_indices]
        cand_z = z[sor_retained_indices]

        envelope_mask_local = (
            (cand_x >= x_min) & (cand_x <= x_max) &
            (cand_y >= y_min) & (cand_y <= y_max) &
            (cand_z >= z_min) & (cand_z <= z_max)
        )

        final_indices = sor_retained_indices[envelope_mask_local]
        num_cleaned = len(final_indices)
        ctx.log_cb(
            f"[SplatCleanup] Final envelope clipping: retained {num_cleaned:,}/{num_raw:,} "
            f"({num_cleaned/num_raw*100:.1f}%), dropped {num_raw - num_cleaned:,} floaters."
        )

        # Write cleaned PLY
        cleaned_vertex = vertex[final_indices]
        cleaned_ply_path = ctx.workdir / "cleaned_splat.ply"

        new_element = PlyElement.describe(cleaned_vertex, "vertex")
        PlyData([new_element], text=False).write(str(cleaned_ply_path))

        elapsed = time.time() - t0
        ctx.log_cb(
            f"[SplatCleanup] Cleaned 3DGS PLY saved ({cleaned_ply_path.stat().st_size:,} bytes) "
            f"with {num_cleaned:,} high-fidelity Gaussians in {elapsed:.1f}s."
        )

        return StageResult(
            success=True,
            output_files=[cleaned_ply_path],
            metadata={
                "raw_gaussians": num_raw,
                "cleaned_gaussians": num_cleaned,
                "retained_fraction": float(num_cleaned / num_raw),
                "elapsed_seconds": elapsed,
            }
        )
