"""
Inverse-Depth Disparity Alignment Stage (Milestone P4 Route B)
Solves scale (s > 0) and shift (t) in inverse-depth space against visible COLMAP sparse points
using RANSAC / Huber loss:
  s_i, t_i = argmin_{s>0, t} || (s * disp_ij + t) - (1.0 / z_sparse_j) ||
Reconstructs metric depth:
  z_hat = 1.0 / max(eps, s_i * disp + t_i)
Clamps max depth to 1.35 * p95(z_sparse), applies bilateral edge-preserving smoothing,
and smooths (s_i, t_i) temporally across adjacent frames.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from scipy.spatial.transform import Rotation as R

from app.pipelines.base import Stage, JobContext, StageResult
from app.utils.logging import logger


def fast_guided_filter(guide: np.ndarray, src: np.ndarray, r: int = 5, eps: float = 1e-3) -> np.ndarray:
    """
    Fast O(1) per-pixel Guided Filter using OpenCV boxFilter.
    Smooths flat planar regions according to RGB frame luminance while snapping sharp depth edges to object borders.
    """
    g = guide.astype(np.float32)
    p = src.astype(np.float32)
    ksize = (2 * r + 1, 2 * r + 1)
    mean_I = cv2.boxFilter(g, cv2.CV_32F, ksize)
    mean_p = cv2.boxFilter(p, cv2.CV_32F, ksize)
    mean_Ip = cv2.boxFilter(g * p, cv2.CV_32F, ksize)
    cov_Ip = mean_Ip - mean_I * mean_p
    mean_II = cv2.boxFilter(g * g, cv2.CV_32F, ksize)
    var_I = mean_II - mean_I * mean_I
    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I
    mean_a = cv2.boxFilter(a, cv2.CV_32F, ksize)
    mean_b = cv2.boxFilter(b, cv2.CV_32F, ksize)
    return mean_a * g + mean_b


def find_colmap_sparse_dir(path: Path) -> Path:
    """
    Locates the directory containing COLMAP sparse model files.
    Prefers text models (sparse_txt, submodels) and auto-converts binary models if needed.
    """
    if (path / "cameras.txt").exists() and (path / "images.txt").exists():
        return path

    candidates = [
        path / "sparse_txt",
        path / "aligned_sparse" / "0",
        path / "aligned_sparse",
        path / "sparse" / "0",
        path / "sparse",
        path / "undistorted" / "sparse",
        path,
    ]
    if path.parent != path:
        candidates.extend([
            path.parent / "sparse_txt",
            path.parent / "aligned_sparse" / "0",
            path.parent / "sparse" / "0",
            path.parent / "undistorted" / "sparse",
            path.parent,
        ])

    for c in candidates:
        if c.is_dir() and (c / "cameras.txt").exists() and (c / "images.txt").exists():
            return c

    # Check for submodels in sparse_txt
    for root_dir in [path, path.parent]:
        submodel_dir = root_dir / "sparse_txt" / "submodels"
        if submodel_dir.is_dir():
            for s in submodel_dir.iterdir():
                if s.is_dir() and (s / "cameras.txt").exists() and (s / "images.txt").exists():
                    return s

    # If only binary .bin files exist, convert them to TXT
    for c in candidates:
        if c.is_dir() and ((c / "cameras.bin").exists() or (c / "images.bin").exists()):
            try:
                from app.pipelines.common.sfm_colmap import resolve_colmap
                from app.pipelines.tool_runner import ToolRunner
                colmap_bin = resolve_colmap()
                workdir = path if (path / "pipeline.log").exists() or (path / "frames").exists() else path.parent
                out_txt = workdir / "sparse_txt"
                out_txt.mkdir(exist_ok=True, parents=True)
                ToolRunner.run([
                    colmap_bin, "model_converter",
                    "--input_path", str(c),
                    "--output_path", str(out_txt),
                    "--output_type", "TXT"
                ], timeout=60)
                if (out_txt / "cameras.txt").exists():
                    return out_txt
            except Exception as e:
                logger.warning(f"[DepthAlign] Failed to auto-convert COLMAP model at {c} to TXT: {e}")

    for c in candidates:
        if c.exists():
            return c
    return path


def parse_colmap_sparse(sparse_dir: Path):
    """
    Parses cameras.txt, images.txt, and points3D.txt from COLMAP sparse reconstruction.
    Returns:
      cams: dict of camera_id -> {fx, fy, cx, cy, width, height}
      images: list of dicts {image_id, name, qvec, tvec, R, t, points2d, point3d_ids}
      points3d: dict of point3d_id -> (X, Y, Z)
    """
    sparse_dir = find_colmap_sparse_dir(sparse_dir)
    cams = {}
    cam_file = sparse_dir / "cameras.txt"
    if cam_file.exists():
        for line in cam_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 5:
                cam_id = int(parts[0])
                model = parts[1].upper()
                w, h = int(parts[2]), int(parts[3])
                if model == "SIMPLE_RADIAL" and len(parts) >= 7:
                    f = float(parts[4])
                    cams[cam_id] = {"fx": f, "fy": f, "cx": float(parts[5]), "cy": float(parts[6]), "w": w, "h": h}
                elif model in {"PINHOLE", "OPENCV"} and len(parts) >= 8:
                    cams[cam_id] = {
                        "fx": float(parts[4]), "fy": float(parts[5]),
                        "cx": float(parts[6]), "cy": float(parts[7]),
                        "w": w, "h": h
                    }
                else:
                    f = float(parts[4])
                    cams[cam_id] = {"fx": f, "fy": f, "cx": w / 2.0, "cy": h / 2.0, "w": w, "h": h}

    points3d = {}
    pts_file = sparse_dir / "points3D.txt"
    if pts_file.exists():
        for line in pts_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                pt_id = int(parts[0])
                xyz = np.array([float(parts[1]), float(parts[2]), float(parts[3])], dtype=np.float32)
                points3d[pt_id] = xyz

    images = []
    img_file = sparse_dir / "images.txt"
    if img_file.exists():
        lines = img_file.read_text().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 10:
                img_id = int(parts[0])
                qw, qx, qy, qz = map(float, parts[1:5])
                tx, ty, tz = map(float, parts[5:8])
                cam_id = int(parts[8])
                name = parts[9]

                r_mat = R.from_quat([qx, qy, qz, qw]).as_matrix().astype(np.float32)
                t_vec = np.array([tx, ty, tz], dtype=np.float32)

                # Next line has 2D points and 3D point IDs
                pts2d = []
                pt3d_ids = []
                if i < len(lines):
                    pt_line = lines[i].strip()
                    i += 1
                    if pt_line and not pt_line.startswith("#"):
                        pt_parts = pt_line.split()
                        for p_idx in range(0, len(pt_parts), 3):
                            if p_idx + 2 < len(pt_parts):
                                u = float(pt_parts[p_idx])
                                v = float(pt_parts[p_idx + 1])
                                p3d_id = int(pt_parts[p_idx + 2])
                                if p3d_id != -1:
                                    pts2d.append((u, v))
                                    pt3d_ids.append(p3d_id)

                images.append({
                    "image_id": img_id,
                    "name": name,
                    "cam_id": cam_id,
                    "R": r_mat,
                    "t": t_vec,
                    "pts2d": np.array(pts2d, dtype=np.float32) if pts2d else np.zeros((0, 2), dtype=np.float32),
                    "pt3d_ids": pt3d_ids,
                })

    return cams, images, points3d


def fit_ransac_inverse_depth(
    pred_disp: np.ndarray,
    inv_depths: np.ndarray,
    max_iters: int = 150,
    inlier_thresh: float = 0.15
) -> Tuple[float, float, int]:
    """
    RANSAC fit for s * disp + t ≈ inv_depth with s > 0 constraint.
    """
    n = len(pred_disp)
    if n < 3:
        return 1.0, 0.0, 0

    best_inliers = 0
    best_s = 1.0
    best_t = 0.0

    for _ in range(max_iters):
        # Sample 2 distinct points
        idx = np.random.choice(n, 2, replace=False)
        d0, d1 = pred_disp[idx[0]], pred_disp[idx[1]]
        z0, z1 = inv_depths[idx[0]], inv_depths[idx[1]]

        denom = d1 - d0
        if abs(denom) < 1e-6:
            continue

        s = (z1 - z0) / denom
        if s <= 1e-4:  # Disparity must have positive correlation with inverse depth
            continue

        t = z0 - s * d0

        # Inlier count based on relative residual
        pred_inv = s * pred_disp + t
        residuals = np.abs(pred_inv - inv_depths) / (np.abs(inv_depths) + 1e-4)
        inlier_mask = residuals < inlier_thresh
        inlier_cnt = int(np.sum(inlier_mask))

        if inlier_cnt > best_inliers:
            best_inliers = inlier_cnt
            # Refit on inliers via robust least squares
            d_in = pred_disp[inlier_mask]
            z_in = inv_depths[inlier_mask]
            if len(d_in) >= 2:
                A = np.column_stack([d_in, np.ones_like(d_in)])
                res = np.linalg.lstsq(A, z_in, rcond=None)[0]
                if res[0] > 0:
                    best_s = float(res[0])
                    best_t = float(res[1])
                else:
                    best_s = float(s)
                    best_t = float(t)
            else:
                best_s = float(s)
                best_t = float(t)

    return best_s, best_t, best_inliers


class DepthAlignStage(Stage):
    """
    Aligns raw monocular disparity to metric/scene depth in inverse-depth space
    using visible COLMAP sparse points.
    """
    name: str = "depth_align"
    weight: float = 2.0
    declared_outputs: List[str] = ["depth_aligned"]

    def run(self, ctx: JobContext) -> StageResult:
        # Skip for Route A (photogrammetry) — OpenMVS provides the mesh directly
        decision_file = ctx.workdir / "mesh_route_decision.json"
        if decision_file.exists():
            try:
                dec = json.loads(decision_file.read_text()).get("decision", "")
                if dec == "photogrammetry":
                    ctx.log_cb("[DepthAlign] Route A (Photogrammetry) active. Skipping depth alignment.")
                    return StageResult(success=True, skipped_cache=True)
            except Exception:
                pass

        ctx.log_cb("[DepthAlign] Initializing inverse-depth disparity alignment...")
        depth_raw_dir = ctx.workdir / "depth_raw"
        if not depth_raw_dir.exists():
            raise FileNotFoundError(f"[DepthAlign] Raw depth directory not found: {depth_raw_dir}")

        depth_aligned_dir = ctx.workdir / "depth_aligned"
        depth_aligned_dir.mkdir(parents=True, exist_ok=True)

        sparse_dir = find_colmap_sparse_dir(ctx.workdir)
        cams, images, points3d = parse_colmap_sparse(sparse_dir)
        if len(images) == 0:
            raise RuntimeError(f"[DepthAlign] No registered images found in COLMAP model at {sparse_dir}")
        ctx.log_cb(f"[DepthAlign] Parsed COLMAP model from {sparse_dir.name}: {len(images)} images, {len(points3d):,} 3D points.")

        # Compute global scene depth distribution across all sparse points
        all_z_sparse: List[float] = []
        for img in images:
            R_mat = img["R"]
            t_vec = img["t"]
            for pt_id in img["pt3d_ids"]:
                if pt_id in points3d:
                    P_w = points3d[pt_id]
                    z_c = float(R_mat[2] @ P_w + t_vec[2])
                    if z_c > 0.05:
                        all_z_sparse.append(z_c)

        if all_z_sparse:
            z_p95 = float(np.percentile(all_z_sparse, 95.0))
            z_max_scene = 1.35 * z_p95
            z_med_scene = float(np.median(all_z_sparse))
            ctx.log_cb(f"[DepthAlign] Sparse depth stats: median={z_med_scene:.2f}, p95={z_p95:.2f}, max_clamp={z_max_scene:.2f}.")
        else:
            z_max_scene = 25.0
            z_med_scene = 3.5

        # Pass 1: Compute raw inverse-depth disparity fits (s_i, t_i) for all frames
        raw_fits = []
        for idx, img in enumerate(images):
            stem = Path(img["name"]).stem
            disp_file = depth_raw_dir / f"{stem}.npy"
            if not disp_file.exists():
                raw_fits.append((1.0, 0.0, 0, None))
                continue

            raw_disp = np.load(str(disp_file)).astype(np.float32)
            h, w = raw_disp.shape[:2]

            R_mat = img["R"]
            t_vec = img["t"]
            pts2d = img["pts2d"]
            p3d_ids = img["pt3d_ids"]

            sampled_disp = []
            sparse_inv_depths = []

            for p_idx, pt_id in enumerate(p3d_ids):
                if pt_id in points3d:
                    P_w = points3d[pt_id]
                    z_c = float(R_mat[2] @ P_w + t_vec[2])
                    if z_c > 0.05:
                        u, v = pts2d[p_idx]
                        u_clamped = int(np.clip(round(u), 0, w - 1))
                        v_clamped = int(np.clip(round(v), 0, h - 1))
                        d_val = float(raw_disp[v_clamped, u_clamped])
                        if d_val > 1e-4:
                            sampled_disp.append(d_val)
                            sparse_inv_depths.append(1.0 / z_c)

            sampled_disp = np.array(sampled_disp, dtype=np.float32)
            sparse_inv_depths = np.array(sparse_inv_depths, dtype=np.float32)

            if len(sampled_disp) >= 6:
                s_est, t_est, inliers = fit_ransac_inverse_depth(sampled_disp, sparse_inv_depths)
            elif len(sampled_disp) >= 1:
                s_est = float(np.median(sparse_inv_depths) / max(np.median(sampled_disp), 1e-4))
                t_est = 0.0
                inliers = len(sampled_disp)
            else:
                s_est, t_est, inliers = 1.0, 0.0, 0

            raw_fits.append((s_est, t_est, inliers, raw_disp))

        # Interpolate frames with low inliers (< 15) from nearest confident neighbors
        valid_indices = [i for i, f in enumerate(raw_fits) if f[2] >= 15]
        if not valid_indices:
            valid_indices = [i for i, f in enumerate(raw_fits) if f[2] >= 5]
        if valid_indices:
            for i, f in enumerate(raw_fits):
                if f[2] < 15:
                    # Find nearest valid index
                    nearest_idx = min(valid_indices, key=lambda vi: abs(vi - i))
                    raw_fits[i] = (raw_fits[nearest_idx][0], raw_fits[nearest_idx][1], f[2], f[3])

        # Pass 2: Bidirectional zero-phase temporal smoothing (Amendment 3)
        n_frames = len(raw_fits)
        s_arr = np.array([f[0] for f in raw_fits], dtype=float)
        t_arr = np.array([f[1] for f in raw_fits], dtype=float)

        alpha_smooth = 0.35
        # Forward EMA
        s_fwd = np.zeros(n_frames, dtype=float)
        t_fwd = np.zeros(n_frames, dtype=float)
        s_fwd[0] = s_arr[0]
        t_fwd[0] = t_arr[0]
        for i in range(1, n_frames):
            s_fwd[i] = alpha_smooth * s_arr[i] + (1.0 - alpha_smooth) * s_fwd[i - 1]
            t_fwd[i] = alpha_smooth * t_arr[i] + (1.0 - alpha_smooth) * t_fwd[i - 1]

        # Backward EMA
        s_bwd = np.zeros(n_frames, dtype=float)
        t_bwd = np.zeros(n_frames, dtype=float)
        s_bwd[-1] = s_arr[-1]
        t_bwd[-1] = t_arr[-1]
        for i in range(n_frames - 2, -1, -1):
            s_bwd[i] = alpha_smooth * s_arr[i] + (1.0 - alpha_smooth) * s_bwd[i + 1]
            t_bwd[i] = alpha_smooth * t_arr[i] + (1.0 - alpha_smooth) * t_bwd[i + 1]

        # Combined bidirectional zero-phase smoothed parameters
        s_smooth_arr = 0.5 * (s_fwd + s_bwd)
        t_smooth_arr = 0.5 * (t_fwd + t_bwd)

        num_aligned = 0
        total_images = len(images)
        alignment_report = []

        prev_depth: Optional[np.ndarray] = None
        prev_gray: Optional[np.ndarray] = None

        frames_dir = ctx.workdir / "frames"
        undist_dir = ctx.workdir / "undistorted" / "images"

        # Pass 3: Reconstruct depth maps, apply TGM damping & RGB-guided filter, and mask occlusion edges
        for idx, img in enumerate(images):
            stem = Path(img["name"]).stem
            s_val = float(s_smooth_arr[idx])
            t_val = float(t_smooth_arr[idx])
            raw_disp = raw_fits[idx][3]
            inliers = raw_fits[idx][2]

            if raw_disp is None:
                continue

            # Reconstruct metric depth: z_hat = 1.0 / max(eps, s * disp + t)
            inv_depth_map = s_val * raw_disp + t_val
            min_inv_depth = 1.0 / max(z_max_scene, 0.1)
            inv_depth_map = np.maximum(inv_depth_map, min_inv_depth)
            depth_map = 1.0 / inv_depth_map
            depth_map = np.clip(depth_map, 0.05, z_max_scene)

            h, w = depth_map.shape[:2]

            # Try to load corresponding RGB image for guidance and TGM damping
            rgb_gray: Optional[np.ndarray] = None
            for cand_path in [
                frames_dir / img["name"],
                frames_dir / Path(img["name"]).name,
                undist_dir / img["name"],
                undist_dir / Path(img["name"]).name,
            ]:
                if cand_path.exists():
                    try:
                        bgr = cv2.imread(str(cand_path))
                        if bgr is not None:
                            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
                            if gray.shape != (h, w):
                                gray = cv2.resize(gray, (w, h), interpolation=cv2.INTER_AREA)
                            rgb_gray = gray
                            break
                    except Exception:
                        pass

            # 1. Flow-free Temporal Gradient Matching (TGM) damping on static low-change pixels
            if rgb_gray is not None and prev_gray is not None and prev_depth is not None:
                if prev_gray.shape == rgb_gray.shape and prev_depth.shape == depth_map.shape:
                    delta_I = np.abs(rgb_gray - prev_gray)
                    # Low-change pixels: damp temporal depth flutter
                    static_mask = (delta_I < 0.05) & (prev_depth > 0.05) & (depth_map > 0.05)
                    depth_map[static_mask] = 0.85 * depth_map[static_mask] + 0.15 * prev_depth[static_mask]

            # 2. RGB-Guided Edge-Preserving Filter (guided by frame luminance)
            if rgb_gray is not None:
                try:
                    guided_depth = fast_guided_filter(rgb_gray, depth_map, r=5, eps=1e-3)
                    valid_g = (guided_depth > 0.05) & (depth_map > 0.05)
                    depth_map[valid_g] = guided_depth[valid_g]
                except Exception:
                    pass

            # 3. 1-pixel finite difference relative step discontinuity check (AFTER RGB guidance)
            # Only mask true occlusion jumps where relative step > 12% in a SINGLE pixel, leaving smooth floors/walls intact
            dz_dx = np.abs(np.diff(depth_map, axis=1, prepend=depth_map[:, :1]))
            dz_dy = np.abs(np.diff(depth_map, axis=0, prepend=depth_map[:1, :]))
            step_rel = np.maximum(dz_dx, dz_dy) / np.maximum(depth_map, 1e-4)
            edge_mask = step_rel > 0.12
            depth_map[edge_mask] = 0.0

            # Bilateral edge-preserving smoothing
            try:
                valid_z = depth_map > 0.05
                depth_smoothed = cv2.bilateralFilter(depth_map, d=5, sigmaColor=0.10 * z_med_scene, sigmaSpace=5.0)
                depth_smoothed[~valid_z] = 0.0
                depth_smoothed[edge_mask] = 0.0
            except Exception:
                depth_smoothed = depth_map

            # Save state for next frame TGM damping
            prev_depth = depth_smoothed.copy()
            prev_gray = rgb_gray.copy() if rgb_gray is not None else None

            # Save aligned 32-bit float metric depth
            out_npy = depth_aligned_dir / f"{stem}.npy"
            np.save(str(out_npy), depth_smoothed.astype(np.float32))

            # Save 16-bit millimeter PNG for fast visualization
            depth_mm = np.clip(depth_smoothed * 1000.0, 0, 65535).astype(np.uint16)
            out_png = depth_aligned_dir / f"{stem}.png"
            cv2.imwrite(str(out_png), depth_mm)

            num_aligned += 1
            alignment_report.append({
                "image": img["name"],
                "sparse_points": len(raw_disp),
                "inliers": inliers,
                "scale": round(s_val, 5),
                "shift": round(t_val, 5),
            })

            if (idx + 1) % 25 == 0 or (idx + 1) == total_images:
                ctx.log_cb(f"[DepthAlign] Aligned {idx+1}/{total_images} frames (scale={s_val:.4f}, shift={t_val:.4f})...")

        # Save alignment telemetry report
        report_file = ctx.workdir / "depth_alignment_report.json"
        report_file.write_text(json.dumps({
            "total_frames_aligned": num_aligned,
            "mean_scale": float(np.mean(s_smooth_arr)) if len(s_smooth_arr) else 1.0,
            "mean_shift": float(np.mean(t_smooth_arr)) if len(t_smooth_arr) else 0.0,
            "max_depth_clamp": z_max_scene,
            "frames": alignment_report[:20],
        }, indent=2))

        ctx.log_cb(f"[DepthAlign] Aligned {num_aligned} metric depth maps in inverse-depth space.")

        return StageResult(
            success=True,
            output_files=[depth_aligned_dir, report_file],
            metadata={"aligned_frames": num_aligned}
        )
