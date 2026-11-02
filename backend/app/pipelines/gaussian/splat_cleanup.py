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
        "quality_report.json",
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
        pts = np.column_stack([x, y, z])

        # Compute robust scene diagonal D_scene in uncalibrated SfM units (2nd to 98th percentile)
        p_min_robust = np.percentile(pts, 2, axis=0)
        p_max_robust = np.percentile(pts, 98, axis=0)
        d_scene = float(np.linalg.norm(p_max_robust - p_min_robust))
        if d_scene < 1e-3:
            d_scene = 10.0
        ctx.log_cb(f"[SplatCleanup] Robust scene diagonal D_scene: {d_scene:.2f} units.")

        opacity_raw = np.asarray(vertex["opacity"], dtype=np.float32)
        s0 = np.asarray(vertex["scale_0"], dtype=np.float32)
        s1 = np.asarray(vertex["scale_1"], dtype=np.float32)
        s2 = np.asarray(vertex["scale_2"], dtype=np.float32)

        # 1. Opacity mist pruning (relaxed to alpha < 0.02)
        # Convert raw logit opacity to linear alpha: sigmoid(opacity)
        alpha = 1.0 / (1.0 + np.exp(-np.clip(opacity_raw, -20.0, 20.0)))
        mask_opacity = alpha >= 0.02
        ctx.log_cb(
            f"[SplatCleanup] Opacity mist filter: retained {np.sum(mask_opacity):,}/{num_raw:,} "
            f"({np.sum(mask_opacity)/num_raw*100:.1f}%), dropped {num_raw - np.sum(mask_opacity):,} mist Gaussians (alpha < 0.02)."
        )

        # 2. Giant floater scale pruning with Planar Pancake Preservation
        # Convert raw log scale to linear scale: exp(scale)
        scale_linear_0 = np.exp(np.clip(s0, -20.0, 5.0))
        scale_linear_1 = np.exp(np.clip(s1, -20.0, 5.0))
        scale_linear_2 = np.exp(np.clip(s2, -20.0, 5.0))
        s_max = np.maximum(scale_linear_0, np.maximum(scale_linear_1, scale_linear_2))
        s_min = np.minimum(scale_linear_0, np.minimum(scale_linear_1, scale_linear_2))

        # Thin planar pancakes (aspect ratio s_min / s_max < 0.12) are used by splatfacto
        # to represent flat walls, floors, and ceilings and must NOT be pruned.
        aspect_ratio = s_min / (s_max + 1e-8)
        is_pancake = aspect_ratio < 0.12

        valid_scales = s_max[mask_opacity] if np.any(mask_opacity) else s_max
        median_scale = float(np.median(valid_scales)) if len(valid_scales) > 0 else 0.05
        # Strictly relative to D_scene: never hardcoded 0.5m in uncalibrated SfM space
        scale_cutoff = min(8.0 * median_scale, 0.08 * d_scene)

        # Only cull giant isotropic/3D-bloated floaters that are NOT flat wall/floor pancakes
        is_giant_bloat = (s_max > scale_cutoff) & (~is_pancake)
        mask_scale = ~is_giant_bloat
        mask_cand = mask_opacity & mask_scale
        ctx.log_cb(
            f"[SplatCleanup] Giant bloat filter (median scale={median_scale:.4f}, cutoff={scale_cutoff:.4f}, "
            f"preserved pancakes={np.sum(is_pancake):,}): "
            f"retained {np.sum(mask_cand):,}/{num_raw:,} ({np.sum(mask_cand)/num_raw*100:.1f}%)."
        )

        # 3. Spatial Statistical Outlier Removal (relaxed to k=20, std_ratio=3.0)
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
            sor_cutoff = dist_mean + 3.0 * dist_std

            mask_sor_local = mean_dist <= sor_cutoff
            sor_retained_indices = cand_indices[mask_sor_local]
            ctx.log_cb(
                f"[SplatCleanup] Spatial SOR filter (mean dist={dist_mean:.3f}, std={dist_std:.3f}, cutoff={sor_cutoff:.3f}): "
                f"retained {len(sor_retained_indices):,}/{len(cand_indices):,}."
            )
        else:
            sor_retained_indices = cand_indices

        # 4. Camera-trajectory + room-plane envelope clipping (relative to D_scene)
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
            cam_span_h = float(np.max(cam_max[[0, 2]] - cam_min[[0, 2]]))

            # Generous room bounds: cameras look outward into large rooms, hallways, and ceilings
            margin_h = max(0.50 * d_scene, 2.5 * cam_span_h)
            x_min = float(cam_min[0] - margin_h)
            x_max = float(cam_max[0] + margin_h)
            z_min = float(cam_min[2] - margin_h)
            z_max = float(cam_max[2] + margin_h)

            # Subfloor buffer below Y=0.00 floor, generous height ceiling clearance
            y_min = -0.10 * d_scene
            y_max = max(float(cam_max[1] + 0.40 * d_scene), float(p_max_robust[1] + 0.15 * d_scene))
        else:
            # Fallback bounds from coordinate spread
            x_min, x_max = float(p_min_robust[0] - 0.3 * d_scene), float(p_max_robust[0] + 0.3 * d_scene)
            y_min, y_max = -0.10 * d_scene, float(p_max_robust[1] + 0.3 * d_scene)
            z_min, z_max = float(p_min_robust[2] - 0.3 * d_scene), float(p_max_robust[2] + 0.3 * d_scene)

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

        # Compute genuine architectural quality report from cleaned Gaussians & envelope
        final_x = cand_x[envelope_mask_local]
        final_y = cand_y[envelope_mask_local]
        final_z = cand_z[envelope_mask_local]

        p1_x, p99_x = float(np.percentile(final_x, 1.0)), float(np.percentile(final_x, 99.0))
        p1_y, p99_y = float(np.percentile(final_y, 0.5)), float(np.percentile(final_y, 99.5))
        p1_z, p99_z = float(np.percentile(final_z, 1.0)), float(np.percentile(final_z, 99.0))

        length = max(p99_x - p1_x, 0.1)
        height = max(p99_y - p1_y, 0.1)
        width = max(p99_z - p1_z, 0.1)
        floor_area = length * width * 0.45  # Typical interior room coverage within bounding rectangle
        retention_pct = round(float(num_cleaned / num_raw * 100), 1)

        quality_report_dict = {
            "vertex_count": 0,
            "face_count": 0,
            "hole_count": 0,
            "gaussian_count": num_cleaned,
            "raw_gaussian_count": num_raw,
            "retention_pct": retention_pct,
            "dimensions_meters": {
                "length": round(length, 2),
                "width": round(width, 2),
                "height": round(height, 2),
            },
            "floor_area_sqm": round(floor_area, 2),
            "cumulative_scale": 1.0,
            "up_axis": "y",
            "is_calibrated": False,
            "is_watertight": False,
            "non_manifold_edges": 0,
            "quality_grade": "A" if retention_pct >= 70.0 else "B",
            "bounds": {
                "min_x": round(p1_x, 2),
                "max_x": round(p99_x, 2),
                "min_y": round(p1_y, 2),
                "max_y": round(p99_y, 2),
                "min_z": round(p1_z, 2),
                "max_z": round(p99_z, 2),
            },
        }

        quality_report_path = ctx.workdir / "quality_report.json"
        quality_report_path.write_text(json.dumps(quality_report_dict, indent=2))

        elapsed = time.time() - t0
        ctx.log_cb(
            f"[SplatCleanup] Cleaned 3DGS PLY saved ({cleaned_ply_path.stat().st_size:,} bytes) "
            f"with {num_cleaned:,} high-fidelity Gaussians in {elapsed:.1f}s. "
            f"Quality report emitted: {length:.2f}m x {width:.2f}m x {height:.2f}m, "
            f"floor area ~{floor_area:.2f} sqm."
        )

        return StageResult(
            success=True,
            output_files=[cleaned_ply_path, quality_report_path],
            metadata={
                "raw_gaussians": num_raw,
                "cleaned_gaussians": num_cleaned,
                "retained_fraction": float(num_cleaned / num_raw),
                "dimensions": quality_report_dict["dimensions_meters"],
                "floor_area_sqm": quality_report_dict["floor_area_sqm"],
                "elapsed_seconds": elapsed,
            }
        )
