"""
Interior-Tuned COLMAP SfM Stage (P2b Diagnostic Pass)
Executes SIFT feature extraction (with GPU/CPU fallback and offscreen Qt),
automatic low-texture frame filtering (Addendum),
sequential and exhaustive matching with auto-retry heuristics,
mapper with model selection and >=60% registration threshold,
sub-model inspection, colmap model_analyzer metrics,
consecutive-camera motion and jump analysis,
multi-panel trajectory diagnostic visualization (camera_path.png),
and comprehensive sfm_report.json output.
"""

import json
import math
import os
import shutil
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.tool_runner import ToolRunner, ToolExecutionError
from app.utils.resource_monitor import ResourceMonitor
from app.pipelines.presets import get_preset_config
from app.utils.tool_resolve import (
    resolve_colmap,
    filter_colmap_args,
    get_configured_threads,
    get_colmap_version,
)
from app.utils.colmap_compat import (
    build_feature_extractor_args,
    build_sequential_matcher_args,
    build_exhaustive_matcher_args,
    build_mapper_args,
    configure_loop_detection,
)


def _quaternion_to_rotation_matrix(q: List[float]) -> np.ndarray:
    """Convert quaternion [qw, qx, qy, qz] to 3x3 rotation matrix with unit normalization."""
    qw, qx, qy, qz = q
    norm = math.sqrt(qw*qw + qx*qx + qy*qy + qz*qz)
    if norm > 1e-9:
        qw, qx, qy, qz = qw / norm, qx / norm, qy / norm, qz / norm
    return np.array([
        [1 - 2*qy**2 - 2*qz**2, 2*qx*qy - 2*qz*qw,     2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw,     1 - 2*qx**2 - 2*qz**2, 2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw,     2*qy*qz + 2*qx*qw,     1 - 2*qx**2 - 2*qy**2]
    ])


def _image_ids_to_pair_id(id1: int, id2: int) -> int:
    """Compute COLMAP pair_id from two image IDs."""
    if id1 > id2:
        id1, id2 = id2, id1
    return 2147483647 * id1 + id2


def _parse_frame_index(name: str) -> int:
    """Extract integer frame index from filename, e.g. frame_000042.jpg -> 42."""
    stem = Path(name).stem
    digits = "".join(ch for ch in stem if ch.isdigit())
    if digits:
        try:
            return int(digits)
        except ValueError:
            pass
    return 0


class ColmapSfMStage(Stage):
    name: str = "sfm_colmap"
    weight: float = 3.0
    declared_outputs: List[str] = [
        "sparse.ply",
        "camera_path.png",
        "sfm_report.json"
    ]

    def _count_registered_images(self, model_dir: Path) -> int:
        """Count registered images in a COLMAP sparse model directory."""
        images_bin = model_dir / "images.bin"
        images_txt = model_dir / "images.txt"

        if images_txt.exists():
            count = 0
            with open(images_txt, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if any(line.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG")):
                            count += 1
            return count

        if images_bin.exists():
            txt_tmp = model_dir / "_inspect_txt"
            txt_tmp.mkdir(exist_ok=True)
            colmap_bin = resolve_colmap()
            try:
                ToolRunner.run([
                    colmap_bin, "model_converter",
                    "--input_path", str(model_dir),
                    "--output_path", str(txt_tmp),
                    "--output_type", "TXT"
                ], timeout=30)
                img_txt = txt_tmp / "images.txt"
                if img_txt.exists():
                    count = 0
                    with open(img_txt, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                if any(line.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG")):
                                    count += 1
                    shutil.rmtree(txt_tmp, ignore_errors=True)
                    return count
            except Exception:
                shutil.rmtree(txt_tmp, ignore_errors=True)

        return 0

    def _find_best_model(self, sparse_dir: Path) -> Tuple[Optional[Path], int]:
        """Find the sparse model directory with the highest number of registered images."""
        if not sparse_dir.exists():
            return None, 0

        subdirs = [d for d in sparse_dir.iterdir() if d.is_dir() and ((d / "cameras.bin").exists() or (d / "cameras.txt").exists())]
        if not subdirs:
            if (sparse_dir / "cameras.bin").exists() or (sparse_dir / "cameras.txt").exists():
                return sparse_dir, self._count_registered_images(sparse_dir)
            return None, 0

        best_dir = None
        max_registered = -1

        for d in sorted(subdirs, key=lambda x: x.name):
            count = self._count_registered_images(d)
            if count > max_registered:
                max_registered = count
                best_dir = d

        return best_dir, max_registered

    def _inspect_all_submodels(self, sparse_dir: Path) -> List[Dict[str, Any]]:
        """Inspect all sub-models in sparse directory and count registered images and 3D points."""
        submodels: List[Dict[str, Any]] = []
        if not sparse_dir.exists():
            return submodels

        subdirs = [d for d in sparse_dir.iterdir() if d.is_dir() and ((d / "cameras.bin").exists() or (d / "cameras.txt").exists())]
        if not subdirs and ((sparse_dir / "cameras.bin").exists() or (sparse_dir / "cameras.txt").exists()):
            subdirs = [sparse_dir]

        for d in sorted(subdirs, key=lambda x: x.name):
            n_imgs = self._count_registered_images(d)
            n_pts = 0
            pts_txt = d / "points3D.txt"
            pts_bin = d / "points3D.bin"
            if pts_txt.exists():
                with open(pts_txt, "r") as f:
                    n_pts = sum(1 for line in f if line.strip() and not line.startswith("#"))
            elif pts_bin.exists():
                txt_tmp = d / "_pts_tmp"
                txt_tmp.mkdir(exist_ok=True)
                try:
                    ToolRunner.run([
                        resolve_colmap(), "model_converter",
                        "--input_path", str(d),
                        "--output_path", str(txt_tmp),
                        "--output_type", "TXT"
                    ], timeout=30)
                    if (txt_tmp / "points3D.txt").exists():
                        with open(txt_tmp / "points3D.txt", "r") as f:
                            n_pts = sum(1 for line in f if line.strip() and not line.startswith("#"))
                except Exception:
                    pass
                finally:
                    shutil.rmtree(txt_tmp, ignore_errors=True)

            submodels.append({
                "submodel_id": d.name,
                "registered_images": n_imgs,
                "point_count": n_pts
            })
        return submodels

    def _filter_low_texture_frames(
        self,
        db_path: Path,
        frames_dir: Path,
        min_keypoints: int,
        ctx: JobContext
    ) -> List[Dict[str, Any]]:
        """
        Inspect per-frame SIFT keypoints in colmap.db and drop very low-texture frames
        (e.g. ceiling-only or blank-wall frames) BEFORE matching.
        """
        dropped: List[Dict[str, Any]] = []
        if not db_path.exists():
            return dropped

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT image_id, name, rows FROM images JOIN keypoints USING(image_id) ORDER BY image_id;")
            rows = cursor.fetchall()
            images_to_delete = []
            for img_id, name, num_kp in rows:
                if num_kp < min_keypoints:
                    f_idx = _parse_frame_index(name)
                    images_to_delete.append((img_id, name, num_kp, f_idx))

            if images_to_delete:
                drop_dir = ctx.workdir / "dropped_low_texture_frames"
                drop_dir.mkdir(parents=True, exist_ok=True)

                for img_id, name, num_kp, f_idx in images_to_delete:
                    cursor.execute("DELETE FROM keypoints WHERE image_id = ?;", (img_id,))
                    cursor.execute("DELETE FROM descriptors WHERE image_id = ?;", (img_id,))
                    cursor.execute("DELETE FROM images WHERE image_id = ?;", (img_id,))

                    # Move file out of frames_dir so matchers don't see it
                    src_frame = frames_dir / name
                    if src_frame.exists():
                        shutil.move(str(src_frame), str(drop_dir / name))

                    dropped.append({
                        "image_id": img_id,
                        "filename": name,
                        "frame_index": f_idx,
                        "keypoint_count": num_kp
                    })
                    ctx.log_cb(
                        f"[SfM] Dropped low-texture frame {name} (index {f_idx}): "
                        f"only {num_kp} SIFT keypoints (< threshold {min_keypoints})."
                    )

                conn.commit()
        finally:
            conn.close()

        return dropped

    def _run_model_analyzer(self, model_dir: Path, colmap_bin: str) -> Dict[str, Any]:
        """Run colmap model_analyzer and extract key metrics."""
        result: Dict[str, Any] = {
            "raw_output": "",
            "mean_track_length": None,
            "observations_per_image": None,
            "points_per_image": None,
        }
        try:
            import re
            cmd = [colmap_bin, "model_analyzer", "--path", str(model_dir)]
            proc = ToolRunner.run(cmd, timeout=60)
            raw_text = proc.stdout if hasattr(proc, "stdout") else str(proc)
            result["raw_output"] = raw_text

            m_track = re.search(r"Mean track length:\s*([0-9.]+)", raw_text)
            if m_track:
                result["mean_track_length"] = round(float(m_track.group(1)), 3)

            m_obs = re.search(r"Mean observations per image:\s*([0-9.]+)", raw_text)
            if m_obs:
                result["observations_per_image"] = round(float(m_obs.group(1)), 3)

            m_pts = re.search(r"Mean points per image:\s*([0-9.]+)", raw_text)
            if m_pts:
                result["points_per_image"] = round(float(m_pts.group(1)), 3)
        except Exception as e:
            result["raw_output"] = f"model_analyzer execution failed: {e}"
        return result

    def _parse_sfm_model(
        self,
        txt_dir: Path,
        all_input_files: List[Path]
    ) -> Tuple[int, float, List[np.ndarray], List[Dict[str, Any]], List[int]]:
        """
        Parse 3D points, mean reprojection error, point positions, registered camera poses,
        and compute unregistered frame indices.
        """
        points_file = txt_dir / "points3D.txt"
        images_file = txt_dir / "images.txt"

        point_count = 0
        total_error = 0.0
        point_coords: List[np.ndarray] = []
        registered_cameras: List[Dict[str, Any]] = []
        registered_names = set()

        if points_file.exists():
            with open(points_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 8:
                        point_count += 1
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        err = float(parts[7])
                        total_error += err
                        if point_count % 3 == 0:  # Sample points for visualization
                            point_coords.append(np.array([x, y, z]))

        mean_error = (total_error / point_count) if point_count > 0 else 0.0

        if images_file.exists():
            with open(images_file, "r") as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 10 and any(parts[9].endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG")):
                        img_id = int(parts[0])
                        qw, qx, qy, qz = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                        tx, ty, tz = float(parts[5]), float(parts[6]), float(parts[7])
                        name = parts[9]
                        registered_names.add(name)
                        r_mat = _quaternion_to_rotation_matrix([qw, qx, qy, qz])
                        t_vec = np.array([tx, ty, tz])
                        cam_center = -r_mat.T @ t_vec
                        f_idx = _parse_frame_index(name)

                        registered_cameras.append({
                            "image_id": img_id,
                            "name": name,
                            "frame_index": f_idx,
                            "quaternion": [qw, qx, qy, qz],
                            "rotation_matrix": r_mat,
                            "translation": t_vec,
                            "cam_center": cam_center
                        })

        registered_cameras.sort(key=lambda c: c["frame_index"])

        unregistered_indices = []
        for f in all_input_files:
            if f.name not in registered_names:
                unregistered_indices.append(_parse_frame_index(f.name))

        unregistered_indices.sort()
        return point_count, mean_error, point_coords, registered_cameras, unregistered_indices

    def _analyze_motion_and_matches(
        self,
        registered_cameras: List[Dict[str, Any]],
        db_path: Path
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, int]]:
        """
        Analyze consecutive camera pairs:
        - Euclidean inter-camera distance
        - Multiple of median distance, flagging jumps > 5x median
        - Relative rotation angle in degrees
        - Rotation-vs-translation measure (deg/m)
        - Verified inlier matches from two_view_geometries table
        """
        per_frame_sift: Dict[str, int] = {}
        verified_matches_lookup: Dict[int, int] = {}

        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name, rows FROM images JOIN keypoints USING(image_id);")
                for name, rows in cursor.fetchall():
                    per_frame_sift[name] = rows

                cursor.execute("SELECT pair_id, rows FROM two_view_geometries;")
                for p_id, rows in cursor.fetchall():
                    verified_matches_lookup[p_id] = rows
            except Exception:
                pass
            finally:
                conn.close()

        if len(registered_cameras) < 2:
            return {"median_distance": 0.0, "consecutive_pairs": []}, [], per_frame_sift

        pairs_data = []
        distances = []

        for k in range(len(registered_cameras) - 1):
            cam_a = registered_cameras[k]
            cam_b = registered_cameras[k + 1]

            d = float(np.linalg.norm(cam_b["cam_center"] - cam_a["cam_center"]))
            distances.append(d)

            r_rel = cam_b["rotation_matrix"] @ cam_a["rotation_matrix"].T
            trace_val = float(np.trace(r_rel))
            cos_theta = max(-1.0, min(1.0, (trace_val - 1.0) / 2.0))
            rot_deg = float(np.degrees(np.arccos(cos_theta)))

            rot_vs_trans = rot_deg / (d + 1e-4)

            p_id = _image_ids_to_pair_id(cam_a["image_id"], cam_b["image_id"])
            inliers = verified_matches_lookup.get(p_id, 0)
            is_gap = (cam_b["frame_index"] != cam_a["frame_index"] + 1)

            pairs_data.append({
                "frame_a": cam_a["name"],
                "frame_b": cam_b["name"],
                "frame_index_a": cam_a["frame_index"],
                "frame_index_b": cam_b["frame_index"],
                "distance": round(d, 4),
                "rotation_deg": round(rot_deg, 2),
                "rot_vs_trans": round(rot_vs_trans, 2),
                "verified_matches": inliers,
                "is_gap": is_gap
            })

        median_dist = float(np.median(distances)) if distances else 1.0
        if median_dist < 1e-6:
            median_dist = 1e-6

        jumps_flagged = []
        for pair in pairs_data:
            multiple = pair["distance"] / median_dist
            pair["median_multiple"] = round(multiple, 2)
            pair["is_jump"] = (multiple > 5.0)
            if pair["is_jump"]:
                jumps_flagged.append({
                    "frame_a": pair["frame_a"],
                    "frame_b": pair["frame_b"],
                    "frame_index_a": pair["frame_index_a"],
                    "frame_index_b": pair["frame_index_b"],
                    "distance": pair["distance"],
                    "median_multiple": pair["median_multiple"],
                    "rotation_deg": pair["rotation_deg"]
                })

        motion_summary = {
            "median_distance": round(median_dist, 4),
            "consecutive_pairs": pairs_data
        }
        return motion_summary, jumps_flagged, per_frame_sift

    def _render_camera_path(
        self,
        registered_cameras: List[Dict[str, Any]],
        point_coords: List[np.ndarray],
        motion_summary: Dict[str, Any],
        jumps_flagged: List[Dict[str, Any]],
        per_frame_sift: Dict[str, int],
        dropped_frames: List[Dict[str, Any]],
        output_path: Path
    ):
        """
        Render comprehensive 4-panel diagnostic figure:
        - Panel 1: Top-Down Trajectory (X-Z) with equal axes, high-contrast points, colored by frame index, broken at gaps/jumps.
        - Panel 2: Side Elevation Trajectory (X vs Elevation -Y) with equal axes, broken at gaps/jumps.
        - Panel 3: Consecutive camera distance (x median, >5x flagged) & relative rotation vs frame index.
        - Panel 4: SIFT keypoints, verified inlier matches, and rotation-vs-translation measure vs frame index.
        """
        if not registered_cameras:
            fig, ax = plt.subplots(figsize=(8, 6), facecolor="#12151e")
            ax.set_facecolor("#191e2b")
            ax.text(0.5, 0.5, "No camera poses registered", color="#94a3b8",
                    ha="center", va="center", fontsize=14)
            plt.savefig(str(output_path), dpi=150, facecolor=fig.get_facecolor())
            plt.close(fig)
            return

        plt.style.use("dark_background")
        fig, axes = plt.subplots(2, 2, figsize=(16, 12), facecolor="#12151e")
        fig.suptitle(
            f"ScanForge SfM Diagnostic & Trajectory Analysis ({len(registered_cameras)} Cameras Registered)",
            fontsize=15, color="#f8fafc", fontweight="bold", y=0.98
        )

        n_cams = len(registered_cameras)
        f_indices = [c["frame_index"] for c in registered_cameras]
        min_f, max_f = min(f_indices), max(f_indices)
        norm = Normalize(vmin=min_f, vmax=max_f if max_f > min_f else min_f + 1)
        cmap = plt.cm.turbo

        cam_lookup = {c["frame_index"]: c for c in registered_cameras}
        pairs_data = motion_summary.get("consecutive_pairs", [])

        # Subsample point coordinates if large
        pts = np.array(point_coords) if point_coords else np.zeros((0, 3))
        if len(pts) > 10000:
            step = len(pts) // 10000
            pts = pts[::step]

        cams_x = [c["cam_center"][0] for c in registered_cameras]
        cams_y = [-c["cam_center"][1] for c in registered_cameras]  # COLMAP Y is down; elevation is -Y
        cams_z = [c["cam_center"][2] for c in registered_cameras]

        # -------------------------------------------------------------
        # Panel 1: Top-Down X-Z Plan View
        # -------------------------------------------------------------
        ax1 = axes[0, 0]
        ax1.set_facecolor("#191e2b")
        ax1.set_title("Top-Down Trajectory (X-Z Plan View)", color="#38bdf8", fontsize=11, pad=8)
        if len(pts) > 0:
            ax1.scatter(pts[:, 0], pts[:, 2], s=2, c="#64748b", alpha=0.35, label="3D Points")

        # Draw trajectory lines broken at gaps or jumps
        for pair in pairs_data:
            if pair["is_gap"] or pair["is_jump"]:
                continue
            idx_a = pair["frame_index_a"]
            idx_b = pair["frame_index_b"]
            if idx_a in cam_lookup and idx_b in cam_lookup:
                c_a = cam_lookup[idx_a]["cam_center"]
                c_b = cam_lookup[idx_b]["cam_center"]
                avg_f = (idx_a + idx_b) / 2
                ax1.plot([c_a[0], c_b[0]], [c_a[2], c_b[2]], color=cmap(norm(avg_f)), lw=2.2)

        # Flagged jumps drawn with red dashed line
        for j in jumps_flagged:
            idx_a = j["frame_index_a"]
            idx_b = j["frame_index_b"]
            if idx_a in cam_lookup and idx_b in cam_lookup:
                c_a = cam_lookup[idx_a]["cam_center"]
                c_b = cam_lookup[idx_b]["cam_center"]
                ax1.plot([c_a[0], c_b[0]], [c_a[2], c_b[2]], color="#ef4444", ls="--", lw=1.6)

        sc1 = ax1.scatter(cams_x, cams_z, c=f_indices, cmap=cmap, norm=norm, s=35, edgecolors="#ffffff", lw=0.6, zorder=5)
        cbar1 = plt.colorbar(sc1, ax=ax1, fraction=0.046, pad=0.04)
        cbar1.set_label("Frame Index", color="#94a3b8", fontsize=9)
        cbar1.ax.tick_params(colors="#94a3b8", labelsize=8)
        ax1.set_xlabel("X (m)", color="#94a3b8", fontsize=9)
        ax1.set_ylabel("Z (m)", color="#94a3b8", fontsize=9)
        ax1.tick_params(colors="#94a3b8", labelsize=8)
        ax1.set_aspect("equal", adjustable="datalim")
        ax1.grid(True, color="#334155", ls=":", alpha=0.5)

        # -------------------------------------------------------------
        # Panel 2: Side Elevation X vs Elevation -Y
        # -------------------------------------------------------------
        ax2 = axes[0, 1]
        ax2.set_facecolor("#191e2b")
        ax2.set_title("Side Elevation Trajectory (X vs Elevation -Y)", color="#38bdf8", fontsize=11, pad=8)
        if len(pts) > 0:
            ax2.scatter(pts[:, 0], -pts[:, 1], s=2, c="#64748b", alpha=0.35)

        for pair in pairs_data:
            if pair["is_gap"] or pair["is_jump"]:
                continue
            idx_a = pair["frame_index_a"]
            idx_b = pair["frame_index_b"]
            if idx_a in cam_lookup and idx_b in cam_lookup:
                c_a = cam_lookup[idx_a]["cam_center"]
                c_b = cam_lookup[idx_b]["cam_center"]
                avg_f = (idx_a + idx_b) / 2
                ax2.plot([c_a[0], c_b[0]], [-c_a[1], -c_b[1]], color=cmap(norm(avg_f)), lw=2.2)

        for j in jumps_flagged:
            idx_a = j["frame_index_a"]
            idx_b = j["frame_index_b"]
            if idx_a in cam_lookup and idx_b in cam_lookup:
                c_a = cam_lookup[idx_a]["cam_center"]
                c_b = cam_lookup[idx_b]["cam_center"]
                ax2.plot([c_a[0], c_b[0]], [-c_a[1], -c_b[1]], color="#ef4444", ls="--", lw=1.6)

        sc2 = ax2.scatter(cams_x, cams_y, c=f_indices, cmap=cmap, norm=norm, s=35, edgecolors="#ffffff", lw=0.6, zorder=5)
        cbar2 = plt.colorbar(sc2, ax=ax2, fraction=0.046, pad=0.04)
        cbar2.set_label("Frame Index", color="#94a3b8", fontsize=9)
        cbar2.ax.tick_params(colors="#94a3b8", labelsize=8)
        ax2.set_xlabel("X (m)", color="#94a3b8", fontsize=9)
        ax2.set_ylabel("Elevation -Y (m)", color="#94a3b8", fontsize=9)
        ax2.tick_params(colors="#94a3b8", labelsize=8)
        ax2.set_aspect("equal", adjustable="datalim")
        ax2.grid(True, color="#334155", ls=":", alpha=0.5)

        # -------------------------------------------------------------
        # Panel 3: Consecutive Camera Motion & Jumps vs Frame
        # -------------------------------------------------------------
        ax3 = axes[1, 0]
        ax3.set_facecolor("#191e2b")
        ax3.set_title("Consecutive Camera Motion & Jumps vs Frame", color="#38bdf8", fontsize=11, pad=8)
        pair_idxs = [p["frame_index_a"] for p in pairs_data]
        multiples = [p["median_multiple"] for p in pairs_data]
        rot_angles = [p["rotation_deg"] for p in pairs_data]

        l1 = ax3.plot(pair_idxs, multiples, color="#38bdf8", marker="o", ms=3.5, lw=1.6, label="Distance (x Median)")
        ax3.axhline(5.0, color="#ef4444", ls="--", lw=1.4, label="5x Median Threshold")
        for j in jumps_flagged:
            ax3.scatter([j["frame_index_a"]], [j["median_multiple"]], color="#ef4444", s=65, marker="x", lw=2.2, zorder=6)

        ax3.set_xlabel("Frame Index", color="#94a3b8", fontsize=9)
        ax3.set_ylabel("Distance / Median Distance", color="#38bdf8", fontsize=9)
        ax3.tick_params(colors="#94a3b8", labelsize=8)
        ax3.grid(True, color="#334155", ls=":", alpha=0.5)

        ax3_twin = ax3.twinx()
        l2 = ax3_twin.plot(pair_idxs, rot_angles, color="#f59e0b", marker="s", ms=3.0, lw=1.4, ls="-.", label="Relative Rotation (deg)")
        ax3_twin.set_ylabel("Rotation (deg)", color="#f59e0b", fontsize=9)
        ax3_twin.tick_params(colors="#f59e0b", labelsize=8)

        all_lines3 = l1 + [ax3.lines[1]] + l2
        all_labels3 = [l.get_label() for l in all_lines3]
        ax3.legend(all_lines3, all_labels3, loc="upper right", facecolor="#1e293b", edgecolor="#475569", fontsize=8)

        # -------------------------------------------------------------
        # Panel 4: Feature Extraction, Inliers & Motion Ratio vs Frame
        # -------------------------------------------------------------
        ax4 = axes[1, 1]
        ax4.set_facecolor("#191e2b")
        ax4.set_title("Feature Extraction, Inliers & Motion Ratio vs Frame", color="#38bdf8", fontsize=11, pad=8)

        sift_counts = [per_frame_sift.get(c["name"], 0) for c in registered_cameras]
        l_kp = ax4.plot(f_indices, sift_counts, color="#22c55e", marker="o", ms=3.0, lw=1.5, label="SIFT Keypoints")
        inliers = [p["verified_matches"] for p in pairs_data]
        l_inl = ax4.plot(pair_idxs, inliers, color="#06b6d4", marker="^", ms=3.0, lw=1.4, ls="--", label="Verified Matches")

        for d in dropped_frames:
            ax4.axvline(d["frame_index"], color="#dc2626", ls=":", lw=1.6, label=f"Dropped (f{d['frame_index']})")

        ax4.set_xlabel("Frame Index", color="#94a3b8", fontsize=9)
        ax4.set_ylabel("Keypoint / Inlier Count", color="#22c55e", fontsize=9)
        ax4.tick_params(colors="#94a3b8", labelsize=8)
        ax4.grid(True, color="#334155", ls=":", alpha=0.5)

        ax4_twin = ax4.twinx()
        rot_trans_vals = [p["rot_vs_trans"] for p in pairs_data]
        l_rt = ax4_twin.plot(pair_idxs, rot_trans_vals, color="#a855f7", ls=":", lw=1.5, label="Rot/Trans Ratio (deg/m)")
        ax4_twin.set_ylabel("Rot/Trans (deg/m)", color="#a855f7", fontsize=9)
        ax4_twin.tick_params(colors="#a855f7", labelsize=8)

        all_lines4 = l_kp + l_inl + l_rt
        all_labels4 = [l.get_label() for l in all_lines4]
        ax4.legend(all_lines4, all_labels4, loc="upper right", facecolor="#1e293b", edgecolor="#475569", fontsize=8)

        plt.tight_layout()
        plt.savefig(str(output_path), dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[SfM] Initializing interior-tuned COLMAP SfM stage...")

        frames_dir = ctx.workdir / "frames"
        if not frames_dir.exists():
            raise FileNotFoundError(f"Frames directory not found in workdir: {frames_dir}")

        image_files = sorted(list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("*.png")))
        total_frames = len(image_files)
        if total_frames == 0:
            raise RuntimeError("No input frames found for COLMAP SfM.")

        ctx.log_cb(f"[SfM] Total input frames for SfM: {total_frames}")

        db_path = ctx.workdir / "colmap.db"
        if db_path.exists():
            db_path.unlink()

        options = ctx.params.get("options", {})
        requested_matcher = options.get("matcher", "sequential")
        camera_model = options.get("camera_model", "SIMPLE_RADIAL")
        quality = ctx.params.get("quality", "standard")

        preset_cfg = get_preset_config(quality)
        max_image_size = str(preset_cfg.colmap_max_image_size)

        colmap_bin = resolve_colmap()
        threads = str(get_configured_threads())

        colmap_env = os.environ.copy()
        colmap_env["QT_QPA_PLATFORM"] = "offscreen"
        if "CUDA_VISIBLE_DEVICES" in os.environ:
            colmap_env["CUDA_VISIBLE_DEVICES"] = os.environ["CUDA_VISIBLE_DEVICES"]

        with ResourceMonitor() as monitor:
            # -------------------------------------------------------------
            # Step 1: Feature Extraction
            # -------------------------------------------------------------
            version = get_colmap_version(colmap_bin)
            ctx.log_cb(
                f"[SfM] Extracting SIFT features (COLMAP v{version[0]}.{version[1]}.{version[2]}, camera model: {camera_model}, "
                f"max size: {max_image_size}px, VRAM: {preset_cfg.vram_gb:.1f}GB, threads: {threads})..."
            )
            extract_args = build_feature_extractor_args(
                version=version,
                database_path=str(db_path),
                image_path=str(frames_dir),
                camera_model=camera_model,
                single_camera=True,
                max_image_size=preset_cfg.colmap_max_image_size,
                use_gpu=True,
                threads=int(threads),
            )
            extract_cmd = [colmap_bin, "feature_extractor"] + extract_args

            use_gpu_sift = True
            try:
                ToolRunner.run(
                    extract_cmd,
                    cwd=str(ctx.workdir),
                    env=colmap_env,
                    log_callback=ctx.log_cb,
                    cancel_token=ctx.cancel_token,
                    timeout=1800
                )
            except ToolExecutionError:
                ctx.log_cb("[SfM] Warning: GPU SIFT extraction failed. Falling back to CPU SIFT extraction...")
                use_gpu_sift = False
                extract_args_cpu = build_feature_extractor_args(
                    version=version,
                    database_path=str(db_path),
                    image_path=str(frames_dir),
                    camera_model=camera_model,
                    single_camera=True,
                    max_image_size=preset_cfg.colmap_max_image_size,
                    use_gpu=False,
                    threads=int(threads),
                )
                extract_cmd_cpu = [colmap_bin, "feature_extractor"] + extract_args_cpu
                ToolRunner.run(
                    extract_cmd_cpu,
                    cwd=str(ctx.workdir),
                    env=colmap_env,
                    log_callback=ctx.log_cb,
                    cancel_token=ctx.cancel_token,
                    timeout=3600
                )

            # -------------------------------------------------------------
            # Step 1b: Low-Texture Frame Filtering (Addendum)
            # -------------------------------------------------------------
            filter_low_texture = options.get("filter_low_texture", True)
            min_sift_keypoints = int(options.get("min_sift_keypoints", 100))
            dropped_frames: List[Dict[str, Any]] = []

            if filter_low_texture and min_sift_keypoints > 0:
                ctx.log_cb(f"[SfM] Checking for low-texture frames (threshold: {min_sift_keypoints} keypoints)...")
                dropped_frames = self._filter_low_texture_frames(
                    db_path=db_path,
                    frames_dir=frames_dir,
                    min_keypoints=min_sift_keypoints,
                    ctx=ctx
                )
                if dropped_frames:
                    ctx.log_cb(f"[SfM] Automatically dropped {len(dropped_frames)} low-texture frames before matching.")
                else:
                    ctx.log_cb("[SfM] All frames meet texture threshold.")
            else:
                ctx.log_cb("[SfM] Low-texture frame filtering disabled.")

            # Update active image files list
            active_image_files = sorted(list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("*.png")))
            active_frame_count = len(active_image_files)
            ctx.log_cb(f"[SfM] Active frames for matching & reconstruction: {active_frame_count}/{total_frames}")

            # -------------------------------------------------------------
            # Step 2: Feature Matching & Mapping
            # -------------------------------------------------------------
            def execute_matcher(m_type: str, gpu_flag: bool, enable_loop_detection: bool = True):
                ctx.log_cb(f"[SfM] Running {m_type} matcher (GPU: {gpu_flag}, threads: {threads})...")
                if m_type == "sequential":
                    loop_enabled = False
                    vocab_path = None
                    if enable_loop_detection:
                        loop_enabled, vocab_path, loop_msg = configure_loop_detection(
                            version=version,
                            custom_vocab_path=options.get("vocab_tree_path"),
                            log_cb=ctx.log_cb,
                        )
                    match_args = build_sequential_matcher_args(
                        version=version,
                        database_path=str(db_path),
                        use_gpu=gpu_flag,
                        threads=int(threads),
                        overlap=25,
                        quadratic_overlap=True,
                        loop_detection=loop_enabled,
                        vocab_tree_path=vocab_path,
                    )
                    match_cmd = [colmap_bin, "sequential_matcher"] + match_args
                else:
                    match_args = build_exhaustive_matcher_args(
                        version=version,
                        database_path=str(db_path),
                        use_gpu=gpu_flag,
                        threads=int(threads),
                    )
                    match_cmd = [colmap_bin, "exhaustive_matcher"] + match_args
                try:
                    ToolRunner.run(
                        match_cmd,
                        cwd=str(ctx.workdir),
                        env=colmap_env,
                        log_callback=ctx.log_cb,
                        cancel_token=ctx.cancel_token,
                        timeout=1800
                    )
                except ToolExecutionError:
                    if m_type == "sequential" and enable_loop_detection:
                        ctx.log_cb(
                            "[SfM] Warning: Sequential matching failed with loop detection. "
                            "Retrying without loop detection..."
                        )
                        execute_matcher("sequential", gpu_flag, enable_loop_detection=False)
                        return

                    if gpu_flag:
                        ctx.log_cb(f"[SfM] Warning: GPU {m_type} matching failed. Falling back to CPU...")
                        execute_matcher(m_type, False, enable_loop_detection=False)
                    else:
                        raise

            def execute_mapper(output_dir: Path, timeout: int = 1800) -> float:
                output_dir.mkdir(parents=True, exist_ok=True)
                ctx.log_cb(f"[SfM] Running COLMAP mapper -> {output_dir.name} (timeout: {timeout}s)...")
                map_args, map_timeout = build_mapper_args(
                    version=version,
                    database_path=str(db_path),
                    image_path=str(frames_dir),
                    output_path=str(output_dir),
                    threads=int(threads),
                    timeout_seconds=timeout,
                    init_min_tri_angle=8.0,
                    filter_min_tri_angle=1.5,
                    ba_use_gpu=False,
                )
                map_cmd = [colmap_bin, "mapper"] + map_args
                import time
                t0 = time.time()
                ToolRunner.run(
                    map_cmd,
                    cwd=str(ctx.workdir),
                    env=colmap_env,
                    log_callback=ctx.log_cb,
                    cancel_token=ctx.cancel_token,
                    timeout=map_timeout
                )
                dur = time.time() - t0
                ctx.log_cb(f"[SfM] Mapper finished in {dur:.1f}s.")
                return dur

            # Initial matching
            sparse_out = ctx.workdir / "sparse"
            execute_matcher(requested_matcher, use_gpu_sift)
            seq_mapper_dur = execute_mapper(sparse_out, timeout=1800)

            best_model_dir, registered_count = self._find_best_model(sparse_out)
            ctx.log_cb(f"[SfM] Initial {requested_matcher} run registered: {registered_count}/{active_frame_count} frames.")

            seq_registered = registered_count if requested_matcher == "sequential" else None
            exh_registered = registered_count if requested_matcher == "exhaustive" else None
            matcher_used = requested_matcher
            exh_mapper_dur: Optional[float] = None

            # Heuristic auto-retry: For <=200 frames, if sequential registers <90%, retry with exhaustive
            if requested_matcher == "sequential" and active_frame_count <= 200 and (registered_count / active_frame_count) < 0.90:
                ctx.log_cb(
                    f"[SfM] Sequential matching registered {registered_count}/{active_frame_count} "
                    f"({(registered_count/active_frame_count)*100:.1f}% < 90%). Retrying with exhaustive matcher..."
                )
                sparse_exh = ctx.workdir / "sparse_exhaustive"
                try:
                    execute_matcher("exhaustive", use_gpu_sift)
                    exh_mapper_dur = execute_mapper(sparse_exh, timeout=1800)

                    exh_model_dir, exh_count = self._find_best_model(sparse_exh)
                    exh_registered = exh_count
                    ctx.log_cb(f"[SfM] Exhaustive matcher registered: {exh_count}/{active_frame_count} frames.")

                    if exh_count > registered_count:
                        ctx.log_cb(f"[SfM] Exhaustive model accepted ({exh_count} > {registered_count} registered frames).")
                        best_model_dir = exh_model_dir
                        registered_count = exh_count
                        matcher_used = "sequential_then_exhaustive"
                    else:
                        ctx.log_cb(f"[SfM] Exhaustive model had fewer or equal registered frames ({exh_count} vs {registered_count}). Keeping sequential model.")
                except Exception as e:
                    ctx.log_cb(f"[SfM] Warning: Exhaustive matcher or mapper failed ({e}). Keeping sequential model.")

            # -------------------------------------------------------------
            # Step 3: Model Conversion, Undistortion & Diagnostics
            # -------------------------------------------------------------
            if best_model_dir is None or registered_count == 0:
                raise RuntimeError("COLMAP reconstruction failed: no valid 3D sparse model could be created.")

            registration_ratio = registered_count / total_frames
            ctx.log_cb(f"[SfM] Final registration ratio: {registered_count}/{total_frames} ({registration_ratio*100:.1f}%)")

            # Sub-model inspection
            active_sparse_dir = ctx.workdir / ("sparse_exhaustive" if matcher_used == "sequential_then_exhaustive" else "sparse")
            sub_models = self._inspect_all_submodels(active_sparse_dir)

            # -------------------------------------------------------------
            # Step 4: Model Conversion & Undistortion
            # -------------------------------------------------------------
            sparse_ply = ctx.workdir / "sparse.ply"
            sparse_txt_dir = ctx.workdir / "sparse_txt"
            sparse_txt_dir.mkdir(exist_ok=True)

            ctx.log_cb("[SfM] Exporting sparse point cloud to PLY and TXT formats...")
            ToolRunner.run([
                colmap_bin, "model_converter",
                "--input_path", str(best_model_dir),
                "--output_path", str(sparse_ply),
                "--output_type", "PLY"
            ], timeout=120)

            ToolRunner.run([
                colmap_bin, "model_converter",
                "--input_path", str(best_model_dir),
                "--output_path", str(sparse_txt_dir),
                "--output_type", "TXT"
            ], timeout=120)

            # Undistort images for downstream P2c (OpenMVS)
            undistorted_dir = ctx.workdir / "undistorted"
            ctx.log_cb("[SfM] Running image undistorter for downstream MVS...")
            ToolRunner.run([
                colmap_bin, "image_undistorter",
                "--image_path", str(frames_dir),
                "--input_path", str(best_model_dir),
                "--output_path", str(undistorted_dir),
                "--output_type", "COLMAP"
            ], timeout=300)

            # Run model_analyzer
            ctx.log_cb("[SfM] Running COLMAP model_analyzer...")
            analyzer_metrics = self._run_model_analyzer(best_model_dir, colmap_bin)

            # Parse model & camera positions
            (point_count, mean_reproj_error, point_coords,
             registered_cameras, unregistered_frame_indices) = self._parse_sfm_model(
                sparse_txt_dir, image_files
            )

            # Consecutive camera motion & verified inlier matches
            motion_summary, jumps_flagged, per_frame_sift = self._analyze_motion_and_matches(
                registered_cameras, db_path
            )

            if jumps_flagged:
                ctx.log_cb(f"[SfM] Motion analysis flagged {len(jumps_flagged)} camera trajectory jumps (>5x median distance).")

            # -------------------------------------------------------------
            # Step 5: Render 4-Panel Trajectory & Diagnostic Figure
            # -------------------------------------------------------------
            camera_path_png = ctx.workdir / "camera_path.png"
            self._render_camera_path(
                registered_cameras=registered_cameras,
                point_coords=point_coords,
                motion_summary=motion_summary,
                jumps_flagged=jumps_flagged,
                per_frame_sift=per_frame_sift,
                dropped_frames=dropped_frames,
                output_path=camera_path_png
            )
            ctx.log_cb(f"[SfM] Saved 4-panel trajectory & diagnostic plot -> {camera_path_png.name}")

        # Compute observations per image from model analyzer if available
        obs_per_image = analyzer_metrics.get("observations_per_image")
        points_per_image = analyzer_metrics.get("points_per_image")
        if points_per_image is None and registered_count > 0:
            points_per_image = round(point_count / registered_count, 1)

        report = {
            "total_frames": total_frames,
            "registered_frames": registered_count,
            "registration_ratio": round(registration_ratio, 3),
            "point_count": point_count,
            "mean_reprojection_error": round(mean_reproj_error, 3),
            "camera_model": camera_model,
            "matcher_used": matcher_used,
            "sequential_registered": seq_registered,
            "exhaustive_registered": exh_registered,
            "mapper_runtime_seconds": exh_mapper_dur if exh_mapper_dur is not None else seq_mapper_dur,
            "mapper_timeout_seconds": 1800,
            "mapper_timeout_fired": False,
            "mean_track_length": analyzer_metrics.get("mean_track_length"),
            "observations_per_image": obs_per_image,
            "points_per_image": points_per_image,
            "sub_models": sub_models,
            "unregistered_frame_indices": unregistered_frame_indices,
            "dropped_low_texture_frames": dropped_frames,
            "jumps_flagged": jumps_flagged,
            "model_analyzer_output": analyzer_metrics.get("raw_output"),
            "motion_analysis": motion_summary,
            "per_frame_sift_keypoints": per_frame_sift,
            "peak_vram_mb": monitor.peak_vram_mb,
            "peak_ram_mb": monitor.peak_ram_mb,
            "sfm_duration_seconds": monitor.elapsed_seconds
        }

        report_file = ctx.workdir / "sfm_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        min_registration_ratio = float(options.get("min_registration_ratio", 0.60))
        fail_on_low_registration = options.get("fail_on_low_registration", False)
        threshold_met = (registration_ratio >= min_registration_ratio)
        report["registration_threshold_met"] = threshold_met

        if not threshold_met:
            warning_msg = (
                f"Registration ratio {registration_ratio*100:.1f}% ({registered_count}/{total_frames} frames) "
                f"is below the target {min_registration_ratio*100:.0f}% threshold. "
                f"Diagnostic plots and SfM reports were preserved."
            )
            ctx.log_cb(f"[SfM Warning] {warning_msg}")
            report["warning"] = warning_msg
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
            if fail_on_low_registration:
                raise RuntimeError(warning_msg)

        ctx.log_cb(
            f"[SfM] Complete! Registered: {registered_count}/{total_frames}, Points: {point_count}, "
            f"Error: {mean_reproj_error:.3f}px, Jumps: {len(jumps_flagged)}, "
            f"VRAM Peak: {monitor.peak_vram_mb:.0f} MB, Elapsed: {monitor.elapsed_seconds:.1f}s"
        )

        return StageResult(
            success=True,
            output_files=[sparse_ply, camera_path_png, report_file],
            metadata=report
        )
