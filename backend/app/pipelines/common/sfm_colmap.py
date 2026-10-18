"""
Interior-Tuned COLMAP SfM Stage
Executes SIFT feature extraction (with GPU/CPU fallback and offscreen Qt),
sequential and exhaustive matching with auto-retry heuristics,
mapper with model selection and >=60% registration threshold,
model conversion to PLY and TXT, image undistortion for downstream MVS,
top-down camera trajectory rendering, and resource metrics reporting.
"""

import json
import math
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np

from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.tool_runner import ToolRunner, ToolExecutionError
from app.services.storage import storage_service
from app.services.job_service import add_artifact
from app.utils.resource_monitor import ResourceMonitor


def _quaternion_to_rotation_matrix(q: List[float]) -> np.ndarray:
    """Convert quaternion [qw, qx, qy, qz] to 3x3 rotation matrix."""
    qw, qx, qy, qz = q
    return np.array([
        [1 - 2*qy**2 - 2*qz**2, 2*qx*qy - 2*qz*qw,     2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw,     1 - 2*qx**2 - 2*qz**2, 2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw,     2*qy*qz + 2*qx*qw,     1 - 2*qx**2 - 2*qy**2]
    ])


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
                        # Every image has two lines in images.txt; count header lines
                        if any(line.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG")):
                            count += 1
            return count

        if images_bin.exists():
            # Run quick model_converter to txt in temp location or read file size
            # If model_converter is available, inspect txt
            txt_tmp = model_dir / "_inspect_txt"
            txt_tmp.mkdir(exist_ok=True)
            try:
                ToolRunner.run([
                    "colmap", "model_converter",
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

        subdirs = [d for d in sparse_dir.iterdir() if d.is_dir() and (d / "cameras.bin").exists() or (d / "cameras.txt").exists()]
        if not subdirs:
            # Check if sparse_dir itself contains cameras.bin
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

    def _parse_sfm_txt_stats(self, txt_dir: Path) -> Tuple[int, float, List[np.ndarray], List[np.ndarray]]:
        """Parse 3D points, mean reprojection error, point positions, and camera positions from TXT model."""
        points_file = txt_dir / "points3D.txt"
        images_file = txt_dir / "images.txt"

        point_count = 0
        total_error = 0.0
        point_coords: List[np.ndarray] = []
        camera_positions: List[np.ndarray] = []

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
                        qw, qx, qy, qz = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                        tx, ty, tz = float(parts[5]), float(parts[6]), float(parts[7])
                        r_mat = _quaternion_to_rotation_matrix([qw, qx, qy, qz])
                        t_vec = np.array([tx, ty, tz])
                        # Camera center C = -R^T * T
                        cam_center = -r_mat.T @ t_vec
                        camera_positions.append(cam_center)

        return point_count, mean_error, point_coords, camera_positions

    def _render_camera_path(
        self,
        camera_positions: List[np.ndarray],
        point_coords: List[np.ndarray],
        output_path: Path
    ):
        """Render a top-down visualization of camera trajectory and 3D points using OpenCV."""
        img_size = 900
        canvas = np.full((img_size, img_size, 3), 24, dtype=np.uint8)  # Dark background #181818

        if not camera_positions:
            cv2.putText(canvas, "No camera poses registered", (100, 450), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (180, 180, 180), 2)
            cv2.imwrite(str(output_path), canvas)
            return

        cam_arr = np.array(camera_positions)
        # Use X and Z for top-down floor-plane view (COLMAP Y is usually down)
        xs = cam_arr[:, 0]
        zs = cam_arr[:, 2]

        min_x, max_x = float(np.min(xs)), float(np.max(xs))
        min_z, max_z = float(np.min(zs)), float(np.max(zs))

        # Add margin
        span_x = max(max_x - min_x, 1.0)
        span_z = max(max_z - min_z, 1.0)
        margin = 80
        scale = (img_size - 2 * margin) / max(span_x, span_z)

        center_x = (min_x + max_x) / 2.0
        center_z = (min_z + max_z) / 2.0

        def to_canvas(x: float, z: float) -> Tuple[int, int]:
            px = int(img_size / 2 + (x - center_x) * scale)
            pz = int(img_size / 2 - (z - center_z) * scale)
            return np.clip(px, 10, img_size - 10), np.clip(pz, 10, img_size - 10)

        # Draw sparse points (subtle gray-blue)
        for pt in point_coords:
            px, pz = to_canvas(pt[0], pt[2])
            cv2.circle(canvas, (px, pz), 1, (90, 80, 60), -1)

        # Draw camera trajectory lines
        for i in range(len(camera_positions) - 1):
            p1 = to_canvas(camera_positions[i][0], camera_positions[i][2])
            p2 = to_canvas(camera_positions[i+1][0], camera_positions[i+1][2])
            cv2.line(canvas, p1, p2, (0, 210, 255), 2, cv2.LINE_AA)  # Cyan trajectory line

        # Draw camera position nodes
        for i, pos in enumerate(camera_positions):
            p = to_canvas(pos[0], pos[2])
            if i == 0:
                cv2.circle(canvas, p, 7, (0, 255, 120), -1, cv2.LINE_AA)  # Start: Bright green
                cv2.putText(canvas, "Start", (p[0] + 10, p[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 120), 1, cv2.LINE_AA)
            elif i == len(camera_positions) - 1:
                cv2.circle(canvas, p, 7, (0, 100, 255), -1, cv2.LINE_AA)  # End: Orange
                cv2.putText(canvas, "End", (p[0] + 10, p[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1, cv2.LINE_AA)
            else:
                cv2.circle(canvas, p, 4, (0, 180, 240), -1, cv2.LINE_AA)

        # Header info overlay
        cv2.putText(canvas, f"ScanForge Camera Trajectory ({len(camera_positions)} cameras)", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2, cv2.LINE_AA)
        cv2.imwrite(str(output_path), canvas)

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

        colmap_env = os.environ.copy()
        colmap_env["QT_QPA_PLATFORM"] = "offscreen"

        with ResourceMonitor() as monitor:
            # -------------------------------------------------------------
            # Step 1: Feature Extraction
            # -------------------------------------------------------------
            ctx.log_cb(f"[SfM] Extracting SIFT features (camera model: {camera_model}, max size: 2000px)...")
            extract_cmd = [
                "colmap", "feature_extractor",
                "--database_path", str(db_path),
                "--image_path", str(frames_dir),
                "--ImageReader.camera_model", camera_model,
                "--ImageReader.single_camera", "1",
                "--SiftExtraction.max_image_size", "2000",
                "--SiftExtraction.use_gpu", "1"
            ]

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
            except ToolExecutionError as e:
                ctx.log_cb("[SfM] Warning: GPU SIFT extraction failed. Falling back to CPU SIFT extraction...")
                use_gpu_sift = False
                extract_cmd_cpu = [
                    "colmap", "feature_extractor",
                    "--database_path", str(db_path),
                    "--image_path", str(frames_dir),
                    "--ImageReader.camera_model", camera_model,
                    "--ImageReader.single_camera", "1",
                    "--SiftExtraction.max_image_size", "2000",
                    "--SiftExtraction.use_gpu", "0"
                ]
                ToolRunner.run(
                    extract_cmd_cpu,
                    cwd=str(ctx.workdir),
                    env=colmap_env,
                    log_callback=ctx.log_cb,
                    cancel_token=ctx.cancel_token,
                    timeout=3600
                )

            # -------------------------------------------------------------
            # Step 2: Feature Matching & Mapping
            # -------------------------------------------------------------
            def execute_matcher(m_type: str, gpu_flag: bool):
                ctx.log_cb(f"[SfM] Running {m_type} matcher (GPU: {gpu_flag})...")
                if m_type == "sequential":
                    match_cmd = [
                        "colmap", "sequential_matcher",
                        "--database_path", str(db_path),
                        "--SiftMatching.use_gpu", "1" if gpu_flag else "0",
                        "--SequentialMatching.overlap", "25",
                        "--SequentialMatching.quadratic_overlap", "1"
                    ]
                else:
                    match_cmd = [
                        "colmap", "exhaustive_matcher",
                        "--database_path", str(db_path),
                        "--SiftMatching.use_gpu", "1" if gpu_flag else "0"
                    ]
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
                    if gpu_flag:
                        ctx.log_cb(f"[SfM] Warning: GPU {m_type} matching failed. Falling back to CPU...")
                        execute_matcher(m_type, False)
                    else:
                        raise

            def execute_mapper(output_dir: Path, timeout: int = 1800):
                output_dir.mkdir(parents=True, exist_ok=True)
                ctx.log_cb(f"[SfM] Running COLMAP mapper -> {output_dir.name}...")
                map_cmd = [
                    "colmap", "mapper",
                    "--database_path", str(db_path),
                    "--image_path", str(frames_dir),
                    "--output_path", str(output_dir),
                    "--Mapper.init_min_tri_angle", "8",
                    "--Mapper.filter_min_tri_angle", "1.5",
                    "--Mapper.ba_global_max_num_iterations", "30",
                    "--Mapper.ba_local_max_num_iterations", "20",
                    "--Mapper.ba_global_max_refinements", "2",
                    "--Mapper.ba_local_max_refinements", "1"
                ]
                ToolRunner.run(
                    map_cmd,
                    cwd=str(ctx.workdir),
                    env=colmap_env,
                    log_callback=ctx.log_cb,
                    cancel_token=ctx.cancel_token,
                    timeout=timeout
                )

            # Initial matching
            sparse_out = ctx.workdir / "sparse"
            execute_matcher(requested_matcher, use_gpu_sift)
            execute_mapper(sparse_out)

            best_model_dir, registered_count = self._find_best_model(sparse_out)
            ctx.log_cb(f"[SfM] Initial {requested_matcher} run registered: {registered_count}/{total_frames} frames.")

            seq_registered = registered_count if requested_matcher == "sequential" else None
            exh_registered = registered_count if requested_matcher == "exhaustive" else None
            matcher_used = requested_matcher

            # Heuristic auto-retry: For <=200 frames, if sequential registers <90%, retry with exhaustive
            if requested_matcher == "sequential" and total_frames <= 200 and (registered_count / total_frames) < 0.90:
                ctx.log_cb(
                    f"[SfM] Sequential matching registered {registered_count}/{total_frames} "
                    f"({(registered_count/total_frames)*100:.1f}% < 90%). Retrying with exhaustive matcher..."
                )
                sparse_exh = ctx.workdir / "sparse_exhaustive"
                try:
                    execute_matcher("exhaustive", use_gpu_sift)
                    execute_mapper(sparse_exh, timeout=600)

                    exh_model_dir, exh_count = self._find_best_model(sparse_exh)
                    exh_registered = exh_count
                    ctx.log_cb(f"[SfM] Exhaustive matcher registered: {exh_count}/{total_frames} frames.")

                    if exh_count > registered_count:
                        ctx.log_cb(f"[SfM] Exhaustive model accepted ({exh_count} > {registered_count} registered frames).")
                        best_model_dir = exh_model_dir
                        registered_count = exh_count
                        matcher_used = "sequential_then_exhaustive"
                    else:
                        ctx.log_cb(f"[SfM] Exhaustive model had fewer or equal registered frames ({exh_count} vs {registered_count}). Keeping sequential model.")
                except Exception as e:
                    ctx.log_cb(f"[SfM] Warning: Exhaustive matcher or mapper failed ({e}). Falling back to sequential model.")

            # -------------------------------------------------------------
            # Step 3: Threshold Validation (Minimum 60%)
            # -------------------------------------------------------------
            if best_model_dir is None or registered_count == 0:
                raise RuntimeError("COLMAP reconstruction failed: no valid 3D sparse model could be created.")

            registration_ratio = registered_count / total_frames
            ctx.log_cb(f"[SfM] Final registration ratio: {registered_count}/{total_frames} ({registration_ratio*100:.1f}%)")

            if registration_ratio < 0.60:
                raise RuntimeError(
                    f"Reconstruction failed: only {registered_count}/{total_frames} frames "
                    f"({registration_ratio*100:.1f}%) were registered during SfM. Minimum required is 60%. "
                    f"Please ensure the scene has sufficient texture and gradual, overlapping motion."
                )

            # -------------------------------------------------------------
            # Step 4: Model Conversion & Undistortion
            # -------------------------------------------------------------
            sparse_ply = ctx.workdir / "sparse.ply"
            sparse_txt_dir = ctx.workdir / "sparse_txt"
            sparse_txt_dir.mkdir(exist_ok=True)

            ctx.log_cb("[SfM] Exporting sparse point cloud to PLY and TXT formats...")
            ToolRunner.run([
                "colmap", "model_converter",
                "--input_path", str(best_model_dir),
                "--output_path", str(sparse_ply),
                "--output_type", "PLY"
            ], timeout=120)

            ToolRunner.run([
                "colmap", "model_converter",
                "--input_path", str(best_model_dir),
                "--output_path", str(sparse_txt_dir),
                "--output_type", "TXT"
            ], timeout=120)

            # Undistort images for downstream P2c (OpenMVS)
            undistorted_dir = ctx.workdir / "undistorted"
            ctx.log_cb("[SfM] Running image undistorter for downstream MVS...")
            ToolRunner.run([
                "colmap", "image_undistorter",
                "--image_path", str(frames_dir),
                "--input_path", str(best_model_dir),
                "--output_path", str(undistorted_dir),
                "--output_type", "COLMAP"
            ], timeout=300)

            # Parse stats
            point_count, mean_reproj_error, point_coords, cam_positions = self._parse_sfm_txt_stats(sparse_txt_dir)

            # -------------------------------------------------------------
            # Step 5: Render Top-Down Camera Path
            # -------------------------------------------------------------
            camera_path_png = ctx.workdir / "camera_path.png"
            self._render_camera_path(cam_positions, point_coords, camera_path_png)
            ctx.log_cb(f"[SfM] Saved camera trajectory plot -> {camera_path_png.name}")

        # Resource stats from ResourceMonitor
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
            "peak_vram_mb": monitor.peak_vram_mb,
            "peak_ram_mb": monitor.peak_ram_mb,
            "sfm_duration_seconds": monitor.elapsed_seconds
        }

        report_file = ctx.workdir / "sfm_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        # Copy and register artifacts
        art_dir = storage_service.get_job_artifacts_dir(ctx.job_id)
        if sparse_ply.exists():
            dest_ply = art_dir / "sparse.ply"
            shutil.copy2(sparse_ply, dest_ply)
            add_artifact(
                job_id=ctx.job_id,
                kind="pointcloud",
                format_name="ply",
                filename="sparse.ply",
                size_bytes=dest_ply.stat().st_size,
                file_path=str(dest_ply)
            )

        if camera_path_png.exists():
            dest_png = art_dir / "camera_path.png"
            shutil.copy2(camera_path_png, dest_png)
            add_artifact(
                job_id=ctx.job_id,
                kind="image",
                format_name="png",
                filename="camera_path.png",
                size_bytes=dest_png.stat().st_size,
                file_path=str(dest_png)
            )

        if report_file.exists():
            dest_rep = art_dir / "sfm_report.json"
            shutil.copy2(report_file, dest_rep)
            add_artifact(
                job_id=ctx.job_id,
                kind="report",
                format_name="json",
                filename="sfm_report.json",
                size_bytes=dest_rep.stat().st_size,
                file_path=str(dest_rep)
            )

        storage_service.create_zip_archive(ctx.job_id)

        ctx.log_cb(
            f"[SfM] Complete! Points: {point_count}, Error: {mean_reproj_error:.3f}px, "
            f"VRAM Peak: {monitor.peak_vram_mb:.0f} MB, RAM Peak: {monitor.peak_ram_mb:.0f} MB, "
            f"Elapsed: {monitor.elapsed_seconds:.1f}s"
        )

        return StageResult(
            success=True,
            output_files=[sparse_ply, camera_path_png, report_file],
            metadata=report
        )
