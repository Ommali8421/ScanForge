"""
Pre-Training Floor Alignment Stage for 3D Gaussian Splatting
Transforms COLMAP sparse reconstruction into the upright Y=0 floor-aligned frame
BEFORE training, ensuring splats sit upright on Y=0 matching our meshes and
Spherical Harmonics suffer zero post-hoc distortion.
"""

import json
import math
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from scipy.spatial.transform import Rotation as R

from app.pipelines.base import Stage, StageResult, JobContext
from app.pipelines.mesh.floor_align import compute_floor_alignment_transform
from app.pipelines.mesh.room_analysis import parse_camera_poses_from_workdir
from app.utils.logging import logger


def align_sparse_model(
    src_sparse_dir: Path,
    dest_sparse_dir: Path,
    R_total: np.ndarray,
    translation: np.ndarray
) -> int:
    """
    Transforms COLMAP cameras, images, and 3D points by rigid transform (R_total, translation).
    Preserves all camera intrinsics and 2D-3D observation tracks.
    Returns number of transformed 3D points.
    """
    dest_sparse_dir.mkdir(parents=True, exist_ok=True)

    # 1. Cameras: Intrinsics remain completely unchanged
    src_cameras = src_sparse_dir / "cameras.txt"
    if src_cameras.exists():
        shutil.copy2(src_cameras, dest_sparse_dir / "cameras.txt")

    # 2. Points3D: X' = R_total @ X + translation
    src_points = src_sparse_dir / "points3D.txt"
    point_count = 0
    if src_points.exists():
        with open(src_points, "r") as fin, open(dest_sparse_dir / "points3D.txt", "w") as fout:
            for line in fin:
                if not line.strip() or line.startswith("#"):
                    fout.write(line)
                    continue
                parts = line.strip().split()
                if len(parts) >= 8:
                    point_count += 1
                    p_id = parts[0]
                    xyz = np.array([float(parts[1]), float(parts[2]), float(parts[3])], dtype=float)
                    rgb = parts[4:7]
                    err = parts[7]
                    track = parts[8:]

                    xyz_transformed = (R_total @ xyz) + translation
                    fout.write(
                        f"{p_id} {xyz_transformed[0]:.6f} {xyz_transformed[1]:.6f} {xyz_transformed[2]:.6f} "
                        f"{' '.join(rgb)} {err} {' '.join(track)}\n"
                    )
                else:
                    fout.write(line)

    # 3. Images: R' = R_orig @ R_total^T, T' = T_orig - R' @ translation
    src_images = src_sparse_dir / "images.txt"
    if src_images.exists():
        with open(src_images, "r") as fin, open(dest_sparse_dir / "images.txt", "w") as fout:
            lines = fin.readlines()
            for line in lines:
                if not line.strip() or line.startswith("#"):
                    fout.write(line)
                    continue
                parts = line.strip().split()
                if len(parts) >= 10 and any(parts[9].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
                    img_id = parts[0]
                    qw, qx, qy, qz = map(float, parts[1:5])
                    tx, ty, tz = map(float, parts[5:8])
                    cam_id = parts[8]
                    img_name = parts[9]

                    # Convert original quaternion to 3x3 rotation matrix
                    r_orig = R.from_quat([qx, qy, qz, qw]).as_matrix()
                    t_orig = np.array([tx, ty, tz], dtype=float)

                    # Transform pose for transformed world coordinates
                    r_new = r_orig @ R_total.T
                    t_new = t_orig - (r_new @ translation)

                    q_new = R.from_matrix(r_new).as_quat()  # [x, y, z, w]
                    new_qx, new_qy, new_qz, new_qw = q_new[0], q_new[1], q_new[2], q_new[3]

                    fout.write(
                        f"{img_id} {new_qw:.8f} {new_qx:.8f} {new_qy:.8f} {new_qz:.8f} "
                        f"{t_new[0]:.6f} {t_new[1]:.6f} {t_new[2]:.6f} {cam_id} {img_name}\n"
                    )
                else:
                    fout.write(line)

    return point_count


class PreTrainFloorAlignStage(Stage):
    """
    Pre-train stage that aligns the COLMAP sparse model so Nerfstudio trains
    directly in the upright Y=0 frame with no post-hoc rotation.
    """
    name: str = "pre_train_floor_align"
    weight: float = 0.5
    declared_outputs: List[str] = [
        "pre_align_metadata.json",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[PreTrainAlign] Preparing pre-training floor alignment in Y=0 frame...")

        # Locate room analysis results
        analysis_file = ctx.workdir / "room_analysis.json"
        if not analysis_file.exists():
            raise FileNotFoundError(f"[PreTrainAlign] room_analysis.json missing in {ctx.workdir}")

        with open(analysis_file, "r") as f:
            analysis = json.load(f)

        chosen_floor = analysis.get("chosen_floor_plane")
        u_grav = np.array(analysis.get("gravity_up_vector", [0.0, 1.0, 0.0]), dtype=float)
        cam_centroid = np.array(analysis.get("camera_centroid", [0.0, 0.0, 0.0]), dtype=float)
        wall_planes = analysis.get("wall_planes", [])
        dominant_wall = np.array(wall_planes[0]["normal"], dtype=float) if wall_planes else None
        scene_diag = float(analysis.get("scene_diagonal", 10.0))

        # Source sparse directory
        src_sparse = ctx.workdir / "sparse_txt"
        if not (src_sparse / "points3D.txt").exists():
            if (ctx.workdir / "sparse" / "0" / "points3D.txt").exists():
                src_sparse = ctx.workdir / "sparse" / "0"
            else:
                sub = list(ctx.workdir.glob("sparse_txt/submodels/*"))
                if sub and (sub[0] / "points3D.txt").exists():
                    src_sparse = sub[0]

        # Load points to compute Y=0 leveling and horizontal centering
        pts_file = src_sparse / "points3D.txt"
        if not pts_file.exists():
            raise FileNotFoundError(f"[PreTrainAlign] points3D.txt missing in {src_sparse}")

        raw_points = []
        with open(pts_file, "r") as f:
            for line in f:
                if not line.strip() or line.startswith("#"):
                    continue
                parts = line.strip().split()
                if len(parts) >= 4:
                    raw_points.append([float(parts[1]), float(parts[2]), float(parts[3])])

        if not raw_points:
            raise ValueError("[PreTrainAlign] Zero 3D points found in sparse model")

        P = np.array(raw_points, dtype=float)

        # 1. Compute rotation to upright target (+Y)
        if chosen_floor is not None:
            fn = np.array(chosen_floor["normal"], dtype=float)
            fd = float(chosen_floor["d"])
        else:
            fn = u_grav
            fd = 0.0

        R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
            floor_normal=fn,
            floor_d=fd,
            cam_centroid=cam_centroid,
            target_up=np.array([0.0, 1.0, 0.0]),
            dominant_wall_normal=dominant_wall,
            u_grav=u_grav
        )

        # 2. Level floor plane to Y = 0.000
        P_rot = P @ R_total.T

        if chosen_floor is not None:
            dists = np.abs(np.dot(P, fn_oriented) + fd_oriented)
            inlier_mask = dists < (0.02 * scene_diag)
            if np.sum(inlier_mask) >= 30:
                y_floor = float(np.median(P_rot[inlier_mask, 1]))
            else:
                p_floor = -fd_oriented * fn_oriented
                y_floor = float((R_total @ p_floor)[1])
        else:
            # Gravity fallback: 5th percentile bottom
            y_floor = float(np.percentile(P_rot[:, 1], 5))

        # 3. Horizontal centering around (0, 0)
        c_x = float((np.min(P_rot[:, 0]) + np.max(P_rot[:, 0])) / 2.0)
        c_z = float((np.min(P_rot[:, 2]) + np.max(P_rot[:, 2])) / 2.0)

        t_vec = np.array([-c_x, -y_floor, -c_z], dtype=float)

        ctx.log_cb(
            f"[PreTrainAlign] Floor leveled: Y_floor={y_floor:.3f}, Center=[{c_x:.3f}, {c_z:.3f}]. "
            f"Transforming COLMAP sparse model..."
        )

        # Output aligned sparse directory
        dest_sparse = ctx.workdir / "aligned_sparse" / "0"
        transformed_pts_count = align_sparse_model(src_sparse, dest_sparse, R_total, t_vec)

        # Prepare Nerfstudio data directory
        ns_data_dir = ctx.workdir / "nerfstudio_data"
        ns_data_dir.mkdir(parents=True, exist_ok=True)
        ns_sparse = ns_data_dir / "sparse" / "0"
        ns_sparse.mkdir(parents=True, exist_ok=True)

        for fname in ["cameras.txt", "images.txt", "points3D.txt"]:
            if (dest_sparse / fname).exists():
                shutil.copy2(dest_sparse / fname, ns_sparse / fname)

        # Link frames
        frames_dir = ctx.workdir / "frames"
        ns_images_link = ns_data_dir / "images"
        if ns_images_link.exists() or ns_images_link.is_symlink():
            if ns_images_link.is_symlink():
                ns_images_link.unlink()
            else:
                shutil.rmtree(ns_images_link)
        try:
            ns_images_link.symlink_to(frames_dir.resolve(), target_is_directory=True)
        except Exception:
            # Copy if symlink not permitted
            shutil.copytree(frames_dir, ns_images_link)

        meta = {
            "R_total": R_total.tolist(),
            "translation": t_vec.tolist(),
            "y_floor": y_floor,
            "center_x": c_x,
            "center_z": c_z,
            "transformed_points": transformed_pts_count,
            "has_verified_floor": chosen_floor is not None,
        }

        meta_file = ctx.workdir / "pre_align_metadata.json"
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        ctx.log_cb(
            f"[PreTrainAlign] Aligned sparse model ready ({transformed_pts_count:,} points). "
            f"Nerfstudio inputs configured in {ns_data_dir}."
        )

        return StageResult(
            success=True,
            output_files=[meta_file],
            metadata={"sparse_points_transformed": transformed_pts_count, "translation": t_vec.tolist()}
        )
