"""
Room Analysis Stage (Phase 2)
Analyzes camera trajectory and interior geometry in the original SfM frame:
- Computes mean camera up-vector (gravity prior).
- Detects dominant planar structures (walls, ceiling, floor) via RANSAC.
- Identifies floor plane via relative, uncalibrated support heuristic.
- Calculates floor-leveling and centering similarity transform.
- Emits room_analysis.json for use by PlaneRepairStage and later FloorAlignStage.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import trimesh

from app.pipelines.base import Stage, StageResult, JobContext


def parse_camera_poses_from_workdir(workdir: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Parses calibrated camera centers and orientations from COLMAP output.
    Returns:
        centers: (N, 3) array of optical centers in world coordinates.
        up_vectors: (N, 3) array of camera up-vectors in world coordinates (u_i = R_w2c^T @ [0, -1, 0]).
        gravity_up: (3,) unit vector pointing along true gravity up, refined via camera trajectory PCA.
    """
    images_txt = workdir / "sparse_txt" / "images.txt"
    if not images_txt.exists():
        # Check submodel directory if present
        submodel_images = list(workdir.glob("sparse_txt/submodels/*/images.txt"))
        if submodel_images:
            images_txt = submodel_images[0]

    centers = []
    up_vectors = []

    if images_txt.exists():
        with open(images_txt, "r") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            # Image line: IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
            if len(parts) >= 10 and (parts[9].lower().endswith(".jpg") or parts[9].lower().endswith(".png")):
                qw, qx, qy, qz = map(float, parts[1:5])
                tx, ty, tz = map(float, parts[5:8])

                # Quaternion to 3x3 rotation matrix R (world to camera)
                R = np.array([
                    [1 - 2*qy**2 - 2*qz**2, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
                    [2*qx*qy + 2*qz*qw, 1 - 2*qx**2 - 2*qz**2, 2*qy*qz - 2*qx*qw],
                    [2*qx*qz - 2*qy*qw, 2*qy*qz + 2*qx*qw, 1 - 2*qx**2 - 2*qy**2]
                ])
                t = np.array([tx, ty, tz])

                # Optical center in world coordinates: C = -R^T * t
                center = -R.T @ t
                # Up vector in world coordinates (camera -Y points up): u = R^T * [0, -1, 0]^T
                up = R.T @ np.array([0.0, -1.0, 0.0])

                centers.append(center)
                up_vectors.append(up)

    if not centers:
        # Fallback to coordinate Y axis if no camera poses found
        return np.zeros((1, 3)), np.array([[0.0, 1.0, 0.0]]), np.array([0.0, 1.0, 0.0])

    centers = np.array(centers)
    up_vectors = np.array(up_vectors)

    mean_up = np.mean(up_vectors, axis=0)
    norm = np.linalg.norm(mean_up)
    if norm > 1e-6:
        mean_up /= norm
    else:
        mean_up = np.array([0.0, 1.0, 0.0])

    # Trajectory PCA Gravity Refinement:
    # When a human walks around a room/floor, the camera positions c_i lie in a flat horizontal plane.
    # The normal to that plane (smallest PCA eigenvector) is orthogonal to the floor,
    # eliminating the 15-20° backward pitch bias caused by holding the camera tilted downwards.
    gravity_up = mean_up.copy()
    if len(centers) >= 8:
        try:
            c_centered = centers - np.mean(centers, axis=0)
            cov = np.cov(c_centered, rowvar=False)
            evals, evecs = np.linalg.eigh(cov)
            # evecs[:, 0] is the normal corresponding to the smallest variance
            traj_normal = evecs[:, 0]
            norm_tn = np.linalg.norm(traj_normal)
            if norm_tn > 1e-6:
                traj_normal /= norm_tn
                # Planarity check: if smallest eigenvalue is small relative to the second eigenvalue
                planarity_ratio = evals[0] / (evals[1] + 1e-9)
                if planarity_ratio < 0.25:
                    # Orient trajectory normal towards mean_up
                    if np.dot(traj_normal, mean_up) < 0:
                        traj_normal = -traj_normal
                    # Use trajectory plane normal as refined gravity up vector
                    gravity_up = traj_normal
        except Exception:
            pass

    return centers, up_vectors, gravity_up


def compute_rodrigues_rotation(v_from: np.ndarray, v_to: np.ndarray) -> np.ndarray:
    """Computes 3x3 rotation matrix rotating v_from to align with v_to."""
    v_from = v_from / (np.linalg.norm(v_from) + 1e-12)
    v_to = v_to / (np.linalg.norm(v_to) + 1e-12)

    cross = np.cross(v_from, v_to)
    dot = float(np.dot(v_from, v_to))

    if dot > 0.999999:
        return np.eye(3)
    if dot < -0.999999:
        # 180 degree rotation around arbitrary orthogonal vector
        axis = np.array([1.0, 0.0, 0.0]) if abs(v_from[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
        ortho = np.cross(v_from, axis)
        ortho /= np.linalg.norm(ortho)
        return 2.0 * np.outer(ortho, ortho) - np.eye(3)

    vx = np.array([
        [0.0, -cross[2], cross[1]],
        [cross[2], 0.0, -cross[0]],
        [-cross[1], cross[0], 0.0]
    ])
    R = np.eye(3) + vx + (vx @ vx) * (1.0 / (1.0 + dot))
    return R


class RoomAnalysisStage(Stage):
    """
    Executes room structure analysis strictly in the original SfM frame:
    1. Extracts camera centers and mean up-vector (gravity prior).
    2. Detects dominant planes (walls, ceiling, floor) via RANSAC.
    3. Evaluates floor candidates with relative scene-scaled rules.
    4. Computes level+center similarity transform.
    5. Saves analysis as room_analysis.json.
    """
    name: str = "room_analysis"
    weight: float = 1.0
    declared_outputs: List[str] = [
        "room_analysis.json",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[RoomAnalysis] Starting interior structural analysis in SfM frame...")
        t0 = time.time()

        input_ply = ctx.workdir / "mesh_cleaned.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "scene_dense_mesh.ply"
        if not input_ply.exists():
            raise FileNotFoundError(f"[RoomAnalysis] Cleaned mesh not found at {input_ply}")

        # 1. Parse camera trajectory & gravity up-vector
        centers, _, u_grav = parse_camera_poses_from_workdir(ctx.workdir)
        cam_median_pos = np.median(centers, axis=0) if len(centers) > 0 else np.zeros(3)
        cam_heights = centers @ u_grav if len(centers) > 0 else np.array([0.0])
        cam_median_height = float(np.median(cam_heights))
        p25_cam = float(np.percentile(cam_heights, 25)) if len(cam_heights) > 0 else cam_median_height
        ctx.log_cb(
            f"[RoomAnalysis] Calibrated cameras: {len(centers)}. "
            f"Gravity up-vector (PCA/trajectory-refined): [{u_grav[0]:.3f}, {u_grav[1]:.3f}, {u_grav[2]:.3f}]. "
            f"Median camera height: {cam_median_height:.3f}, p25 camera height: {p25_cam:.3f} (SfM units)."
        )

        # 2. Load mesh and calculate scene bounds & vertex height percentiles
        mesh = trimesh.load(str(input_ply), process=False)
        vertices = mesh.vertices
        bbox_min = np.min(vertices, axis=0)
        bbox_max = np.max(vertices, axis=0)
        scene_diagonal = float(np.linalg.norm(bbox_max - bbox_min))

        v_heights = vertices @ u_grav
        p10_verts = float(np.percentile(v_heights, 10))
        p30_verts = float(np.percentile(v_heights, 30))
        p50_verts = float(np.percentile(v_heights, 50))
        ctx.log_cb(
            f"[RoomAnalysis] Scene bounds: [{bbox_min[0]:.2f}, {bbox_min[1]:.2f}, {bbox_min[2]:.2f}] to "
            f"[{bbox_max[0]:.2f}, {bbox_max[1]:.2f}, {bbox_max[2]:.2f}]. "
            f"Scene diagonal: {scene_diagonal:.3f} (SfM units). "
            f"Vertex heights along u_grav: 10%={p10_verts:.3f}, 30%={p30_verts:.3f}, 50%={p50_verts:.3f}."
        )

        # 3. Detect dominant planes via iterative RANSAC
        import open3d as o3d
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(vertices)

        # Downsample point cloud for fast robust RANSAC if very dense
        voxel_size = max(0.005 * scene_diagonal, 0.02)
        if len(vertices) > 100_000:
            pcd_sampled = pcd.voxel_down_sample(voxel_size)
        else:
            pcd_sampled = pcd

        remaining_pcd = pcd_sampled
        detected_planes = []
        ransac_distance_threshold = max(0.006 * scene_diagonal, 0.025)
        min_inliers_count = max(200, int(len(pcd_sampled.points) * 0.015))

        ctx.log_cb(
            f"[RoomAnalysis] Running RANSAC plane detection (dist_thresh={ransac_distance_threshold:.3f}, "
            f"min_inliers={min_inliers_count:,})..."
        )

        for plane_idx in range(8):
            if len(remaining_pcd.points) < min_inliers_count:
                break
            try:
                plane_model, inliers = remaining_pcd.segment_plane(
                    distance_threshold=ransac_distance_threshold,
                    ransac_n=3,
                    num_iterations=1000,
                )
            except Exception:
                break

            if len(inliers) < min_inliers_count:
                break

            a, b, c, d = plane_model
            norm_abc = np.linalg.norm([a, b, c])
            if norm_abc < 1e-6:
                break
            n = np.array([a, b, c]) / norm_abc
            d_norm = d / norm_abc

            # Remove inliers from remaining cloud
            remaining_pcd = remaining_pcd.select_by_index(inliers, invert=True)

            detected_planes.append({
                "index": plane_idx,
                "normal": [float(n[0]), float(n[1]), float(n[2])],
                "d": float(d_norm),
                "inliers": len(inliers),
            })

        ctx.log_cb(f"[RoomAnalysis] Detected {len(detected_planes)} dominant plane candidate(s).")

        # 4. Classify planes: Horizontal vs Vertical
        horizontal_planes = []
        wall_planes = []

        for p in detected_planes:
            n = np.array(p["normal"])
            d = p["d"]
            cos_up = float(np.dot(n, u_grav))

            # If nearly parallel to gravity up: horizontal
            if abs(cos_up) >= 0.80:
                # Orient normal strictly pointing in +u_grav direction
                if cos_up < 0:
                    n = -n
                    d = -d
                    cos_up = -cos_up
                # Plane height along gravity vector: point on plane is p0 = -d * n
                # height = p0 . u_grav = -d * (n . u_grav)
                h_plane = float(-d * cos_up)
                horizontal_planes.append({
                    "normal": [float(n[0]), float(n[1]), float(n[2])],
                    "d": float(d),
                    "inliers": p["inliers"],
                    "height": h_plane,
                    "cos_up": cos_up,
                })
            elif abs(cos_up) <= 0.25:
                # Vertical plane (wall)
                # Orient normal pointing toward camera trajectory median center
                p0 = -d * n
                if np.dot(n, cam_median_pos - p0) < 0:
                    n = -n
                    d = -d
                wall_planes.append({
                    "normal": [float(n[0]), float(n[1]), float(n[2])],
                    "d": float(d),
                    "inliers": p["inliers"],
                })

        # 5. Relative Floor Selection Heuristic & Ceiling-as-Floor Guard
        # Mandatory requirements:
        # 1. Floor plane MUST lie below at least 75% of camera centers: h <= p25_cam
        # 2. Floor plane MUST lie within lowest 30% of dense point cloud: h <= p30_verts
        # 3. Normal aligned with +u_grav: dot(n_floor, u_grav) >= 0.80
        # 4. Ceiling rejection: any plane at/above camera median or above 50% vertices is strictly rejected
        floor_candidates = []
        min_floor_support = max(100, int(len(pcd_sampled.points) * 0.015))

        for hp in horizontal_planes:
            h = hp["height"]
            depth_below_cam = cam_median_height - h

            is_below_75pct_cams = h <= (p25_cam + 0.02 * scene_diagonal)
            is_in_lowest_30pct_verts = h <= (p30_verts + 0.02 * scene_diagonal)
            is_not_ceiling = (h < cam_median_height) and (h < p50_verts)
            has_enough_support = hp["inliers"] >= min_floor_support

            qualifies = bool(
                is_below_75pct_cams and
                is_in_lowest_30pct_verts and
                is_not_ceiling and
                has_enough_support
            )

            hp["depth_below_camera"] = float(depth_below_cam)
            hp["depth_fraction"] = float(depth_below_cam / scene_diagonal)
            hp["qualifies"] = qualifies
            if not qualifies:
                reasons = []
                if not is_below_75pct_cams:
                    reasons.append("above 25th percentile camera centers")
                if not is_in_lowest_30pct_verts:
                    reasons.append("above 30th percentile point cloud")
                if not is_not_ceiling:
                    reasons.append("ceiling/upper structure above cameras")
                if not has_enough_support:
                    reasons.append(f"inliers {hp['inliers']} < {min_floor_support}")
                hp["rejection_reason"] = "; ".join(reasons)

            floor_candidates.append(hp)

        qualifying_floors = [c for c in floor_candidates if c["qualifies"]]

        if qualifying_floors:
            # Sort by planar inlier support descending; break ties by lower height (ground floor below elevated furniture)
            qualifying_floors.sort(key=lambda x: (x["inliers"], -x["height"]), reverse=True)
            chosen_floor = qualifying_floors[0]
            ctx.log_cb(
                f"[RoomAnalysis] Identified verified floor from {len(qualifying_floors)} qualifying candidate(s): "
                f"Height={chosen_floor['height']:.3f}, depth_below_cam={chosen_floor['depth_below_camera']:.3f} "
                f"({chosen_floor['depth_fraction']*100:.1f}% diag), inliers={chosen_floor['inliers']:,}."
            )
        else:
            # Mandatory Gravity Fallback: Never pick a ceiling plane as floor!
            chosen_floor = None
            ctx.log_cb(
                f"[RoomAnalysis] No horizontal plane satisfied verified floor criteria (all were ceiling, upper structures, or low support). "
                f"Setting chosen_floor_plane = None to trigger mandatory gravity fallback."
            )

        # 6. Compute Floor Leveling & Centering Transform
        # If valid floor exists: align floor normal to +Y: [0, 1, 0]^T
        # If chosen_floor is None: rotate u_grav to +Y: [0, 1, 0]^T and level bottom vertices
        if chosen_floor is not None:
            n_floor_vec = np.array(chosen_floor["normal"])
            R_level = compute_rodrigues_rotation(n_floor_vec, np.array([0.0, 1.0, 0.0]))
            p_floor = -chosen_floor["d"] * n_floor_vec
            p_floor_leveled = R_level @ p_floor
            ty = -p_floor_leveled[1]
        else:
            R_level = compute_rodrigues_rotation(u_grav, np.array([0.0, 1.0, 0.0]))
            v_rot_y = (vertices @ R_level.T)[:, 1]
            p5_y = float(np.percentile(v_rot_y, 5))
            ty = -p5_y

        # Horizontal centering: center camera median horizontal position at X=0, Z=0
        cam_leveled = R_level @ cam_median_pos
        tx = -cam_leveled[0]
        tz = -cam_leveled[2]

        T_level_center = np.eye(4)
        T_level_center[:3, :3] = R_level
        T_level_center[:3, 3] = np.array([tx, ty, tz])

        # 7. Save room_analysis.json
        cam_min = np.min(centers, axis=0) if len(centers) > 0 else bbox_min
        cam_max = np.max(centers, axis=0) if len(centers) > 0 else bbox_max
        report_data = {
            "camera_mean_up": [float(x) for x in u_grav],
            "gravity_up_vector": [float(x) for x in u_grav],
            "median_camera_height": cam_median_height,
            "scene_diagonal": scene_diagonal,
            "bounding_box_min": [float(x) for x in bbox_min],
            "bounding_box_max": [float(x) for x in bbox_max],
            "cam_bbox_min": [float(x) for x in cam_min],
            "cam_bbox_max": [float(x) for x in cam_max],
            "floor_candidates": floor_candidates,
            "chosen_floor_plane": chosen_floor,
            "wall_planes": wall_planes,
            "total_dominant_planes_detected": len(detected_planes),
            "level_center_transform": T_level_center.tolist(),
        }

        output_json = ctx.workdir / "room_analysis.json"
        with open(output_json, "w") as f:
            json.dump(report_data, f, indent=2)

        ctx.log_cb(f"[RoomAnalysis] Saved structural analysis to {output_json.name} in {time.time() - t0:.2f}s.")

        return StageResult(
            success=True,
            output_files=[output_json],
            metadata=report_data,
        )
