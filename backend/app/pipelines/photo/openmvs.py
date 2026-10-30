"""
OpenMVS Pipeline Stages (Milestone P2c Phase 1b)
Wrappers for InterfaceCOLMAP, DensifyPointCloud, ReconstructMesh, and TextureMesh.
Adheres to ScanForge Portability & Resource Etiquette Rules:
1. Dynamic OpenMVS binary resolution.
2. Dynamic working resolution derived from actual image dimensions and VRAM tier.
3. Automatic low-memory OOM retry (bumps resolution level).
4. RAM guard for 11 GB WSL environment.
5. Obvious garbage removal: OpenMVS spurious/spikes/hole-closing + Python edge-length (>6x median) and expanded camera bbox filtering.
6. Nearest-neighbor vertex color transfer from dense point cloud for raw/preview meshes.
7. Mean camera up-vector alignment (up = +Y) for glTF/PLY previews.
8. UV Texture atlas generation via TextureMesh + oriented preview_textured.glb.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.tool_runner import ToolRunner
from app.utils.logging import logger
from app.utils.tool_resolve import (
    resolve_openmvs,
    resolve_colmap,
    get_configured_threads,
    get_available_vram_gb,
    check_ram_guard,
    determine_openmvs_resolution_level,
)


def qvec2rotmat(qvec: np.ndarray) -> np.ndarray:
    """Convert COLMAP quaternion [qw, qx, qy, qz] to 3x3 rotation matrix (world to camera)."""
    return np.array([
        [1 - 2 * qvec[2]**2 - 2 * qvec[3]**2,
         2 * qvec[1] * qvec[2] - 2 * qvec[0] * qvec[3],
         2 * qvec[1] * qvec[3] + 2 * qvec[0] * qvec[2]],
        [2 * qvec[1] * qvec[2] + 2 * qvec[0] * qvec[3],
         1 - 2 * qvec[1]**2 - 2 * qvec[3]**2,
         2 * qvec[2] * qvec[3] - 2 * qvec[0] * qvec[1]],
        [2 * qvec[1] * qvec[3] - 2 * qvec[0] * qvec[2],
         2 * qvec[2] * qvec[3] + 2 * qvec[0] * qvec[1],
         1 - 2 * qvec[1]**2 - 2 * qvec[2]**2]
    ])


def compute_alignment_rotation(mean_up: np.ndarray, target_up: np.ndarray = np.array([0.0, 1.0, 0.0])) -> np.ndarray:
    """
    Compute 3x3 rotation matrix that rotates mean_up to target_up using Rodrigues formula.
    """
    v1 = mean_up / np.linalg.norm(mean_up)
    v2 = target_up / np.linalg.norm(target_up)

    axis = np.cross(v1, v2)
    axis_norm = np.linalg.norm(axis)
    dot = np.dot(v1, v2)

    if axis_norm < 1e-7:
        if dot > 0:
            return np.eye(3)
        else:
            # 180 degree rotation around X
            return np.diag([1.0, -1.0, -1.0])

    axis = axis / axis_norm
    angle = np.arccos(np.clip(dot, -1.0, 1.0))

    K = np.array([
        [0.0, -axis[2], axis[1]],
        [axis[2], 0.0, -axis[0]],
        [-axis[1], axis[0], 0.0]
    ])
    R = np.eye(3) + np.sin(angle) * K + (1.0 - np.cos(angle)) * (K @ K)
    return R


def parse_camera_poses_and_up_vector(workdir: Path) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray], np.ndarray]:
    """
    Parse registered camera poses from sparse_txt/images.txt (or convert from images.bin).
    Computes:
    - mean_up: normalized mean camera up vector in world coordinates (mean of R_i^T [0, -1, 0])
    - cam_min: min (x, y, z) camera center
    - cam_max: max (x, y, z) camera center
    - R_align: 3x3 rotation matrix aligning mean_up to [0, 1, 0] (up = +Y)
    """
    txt_path = workdir / "sparse_txt" / "images.txt"
    if not txt_path.exists():
        # Check undistorted/sparse or sparse/0
        sparse_bin_dir = workdir / "undistorted" / "sparse"
        if not (sparse_bin_dir / "images.bin").exists():
            sparse_bin_dir = workdir / "sparse" / "0"

        if (sparse_bin_dir / "images.bin").exists():
            try:
                tmp_txt_dir = workdir / "_temp_cam_txt"
                tmp_txt_dir.mkdir(exist_ok=True)
                colmap_bin = resolve_colmap()
                ToolRunner.run([
                    colmap_bin, "model_converter",
                    "--input_path", str(sparse_bin_dir),
                    "--output_path", str(tmp_txt_dir),
                    "--output_type", "TXT"
                ], timeout=30)
                txt_path = tmp_txt_dir / "images.txt"
            except Exception:
                pass

    if not txt_path.exists():
        logger.warning(f"[OpenMVS] Could not find camera poses in {workdir}; defaulting to identity alignment.")
        return None, None, None, np.eye(3)

    cams = []
    up_vecs = []

    try:
        with open(txt_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 10 and any(parts[-1].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
                    qvec = np.array([float(x) for x in parts[1:5]])
                    tvec = np.array([float(x) for x in parts[5:8]])
                    R = qvec2rotmat(qvec)
                    # Camera center C = -R.T @ t
                    C = -R.T @ tvec
                    # Up vector in world coordinates: u = R.T @ [0, -1, 0]
                    u = R.T @ np.array([0.0, -1.0, 0.0])
                    cams.append(C)
                    up_vecs.append(u)
    except Exception as e:
        logger.warning(f"[OpenMVS] Error parsing {txt_path}: {e}")

    if not cams or not up_vecs:
        return None, None, None, np.eye(3)

    cams_arr = np.array(cams)
    up_arr = np.array(up_vecs)

    cam_min = np.min(cams_arr, axis=0)
    cam_max = np.max(cams_arr, axis=0)

    mean_up = np.mean(up_arr, axis=0)
    norm = np.linalg.norm(mean_up)
    if norm > 1e-6:
        mean_up = mean_up / norm
    else:
        mean_up = np.array([0.0, 1.0, 0.0])

    R_align = compute_alignment_rotation(mean_up)
    return mean_up, cam_min, cam_max, R_align


class OpenMVSInterfaceStage(Stage):
    """
    Exports COLMAP undistorted model to OpenMVS scene format (scene.mvs).
    """
    name: str = "openmvs_interface"
    weight: float = 0.5
    declared_outputs: List[str] = ["scene.mvs"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Preparing COLMAP model for MVS reconstruction...")
        interface_bin = resolve_openmvs("InterfaceCOLMAP")
        threads = str(get_configured_threads())

        undistorted_dir = ctx.workdir / "undistorted"
        if not undistorted_dir.exists():
            raise FileNotFoundError(
                f"Undistorted COLMAP folder not found at {undistorted_dir}. "
                "Ensure ColmapSfMStage ran successfully."
            )

        output_mvs = ctx.workdir / "scene.mvs"
        cmd = [
            interface_bin,
            "-w", str(ctx.workdir),
            "-i", "undistorted",
            "-o", "scene.mvs",
            "--image-folder", "undistorted/images",
            "--max-threads", threads,
            "-v", "2",
        ]

        ctx.log_cb(f"[OpenMVS] Running InterfaceCOLMAP -> {output_mvs.name} (threads: {threads})")
        res = ToolRunner.run(
            cmd,
            cwd=str(ctx.workdir),
            log_callback=ctx.log_cb,
            cancel_token=ctx.cancel_token,
            timeout=300,
        )

        if not output_mvs.exists():
            raise RuntimeError(
                f"InterfaceCOLMAP completed with exit code {res.exit_code} "
                f"but output {output_mvs} was not created."
            )

        ctx.log_cb(f"[OpenMVS] Scene interface created successfully: {output_mvs.name} ({output_mvs.stat().st_size / 1024:.1f} KB)")
        return StageResult(
            success=True,
            output_files=[output_mvs],
            metadata={"mvs_file": str(output_mvs.name)},
        )


class OpenMVSDensifyStage(Stage):
    """
    Computes dense point cloud from scene.mvs using OpenMVS DensifyPointCloud.
    Resolution level is dynamically selected based on image size and VRAM tier,
    with automatic OOM fallback retry.
    """
    name: str = "openmvs_densify"
    weight: float = 3.0
    declared_outputs: List[str] = ["scene_dense.mvs", "scene_dense.ply", "dense_cloud.ply"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Initializing dense point cloud reconstruction (DensifyPointCloud)...")
        densify_bin = resolve_openmvs("DensifyPointCloud")
        threads = str(get_configured_threads())

        # Check RAM guard for 11 GB WSL
        is_safe, avail_mb, total_mb = check_ram_guard(min_available_mb=1500)
        ctx.log_cb(f"[RAM Guard] Host memory check: {avail_mb:.1f} MB available / {total_mb:.1f} MB total (safe: {is_safe})")

        # Determine input image dimensions
        img_w, img_h = 1080, 1920
        ingest_meta_file = ctx.workdir / "ingest_metadata.json"
        if ingest_meta_file.exists():
            try:
                with open(ingest_meta_file, "r") as f:
                    meta = json.load(f)
                    img_w = meta.get("effective_width") or meta.get("width") or img_w
                    img_h = meta.get("effective_height") or meta.get("height") or img_h
            except Exception:
                pass

        vram_gb = get_available_vram_gb()
        quality = ctx.params.get("quality", "standard")
        initial_res_level = determine_openmvs_resolution_level(img_w, img_h, vram_gb=vram_gb, quality=quality)

        ctx.log_cb(
            f"[OpenMVS] Dynamic resolution planning: frame={img_w}x{img_h}, VRAM={vram_gb:.1f} GB, "
            f"quality='{quality}' -> initial resolution-level {initial_res_level}"
        )

        input_mvs = ctx.workdir / "scene.mvs"
        output_mvs = ctx.workdir / "scene_dense.mvs"
        output_ply = ctx.workdir / "scene_dense.ply"

        if not input_mvs.exists():
            raise FileNotFoundError(f"Input scene file not found: {input_mvs}")

        # Execution with OOM auto-retry
        res_level = initial_res_level
        max_retries = 2
        success = False
        last_error = ""

        for attempt in range(max_retries + 1):
            cmd = [
                densify_bin,
                "-w", str(ctx.workdir),
                "-i", "scene.mvs",
                "-o", "scene_dense.mvs",
                "--resolution-level", str(res_level),
                "--max-threads", threads,
                "-v", "2",
            ]

            ctx.log_cb(f"[OpenMVS] Running DensifyPointCloud (attempt {attempt+1}, resolution-level {res_level}, threads {threads})...")
            try:
                res = ToolRunner.run(
                    cmd,
                    cwd=str(ctx.workdir),
                    log_callback=ctx.log_cb,
                    cancel_token=ctx.cancel_token,
                    timeout=1800,
                )

                if output_mvs.exists() and output_ply.exists():
                    success = True
                    break
                else:
                    last_error = f"DensifyPointCloud exited with code {res.exit_code} without generating outputs."
            except Exception as e:
                err_msg = str(e)
                last_error = err_msg
                is_oom = any(k in err_msg.lower() for k in ("out of memory", "cuda error", "std::bad_alloc", "oom"))
                if is_oom and attempt < max_retries:
                    res_level += 1
                    ctx.log_cb(
                        f"[OpenMVS] WARNING: Memory pressure / CUDA OOM detected during densification. "
                        f"Retrying automatically at lower resolution-level {res_level}..."
                    )
                    continue
                raise

        if not success:
            raise RuntimeError(f"Dense point cloud reconstruction failed: {last_error}")

        # Parse number of dense points from generated ply or log
        point_count = 0
        try:
            if output_ply.exists():
                with open(output_ply, "rb") as f:
                    for _ in range(30):
                        line = f.readline().decode("ascii", errors="ignore")
                        if line.startswith("element vertex"):
                            point_count = int(line.split()[-1])
                            break
        except Exception:
            pass

        ctx.log_cb(f"[OpenMVS] Dense point cloud generated: {point_count:,} points ({output_ply.stat().st_size / (1024*1024):.1f} MB)")

        # Create standardized preview artifact
        dense_preview = ctx.workdir / "dense_cloud.ply"
        if not dense_preview.exists() and output_ply.exists():
            shutil.copyfile(output_ply, dense_preview)

        return StageResult(
            success=True,
            output_files=[output_mvs, output_ply, dense_preview],
            metadata={
                "point_count": point_count,
                "resolution_level": res_level,
                "dense_ply": str(output_ply.name),
                "preview_ply": str(dense_preview.name),
            },
        )


class OpenMVSRMeshStage(Stage):
    """
    Reconstructs surface mesh from dense point cloud using OpenMVS ReconstructMesh.
    Applies:
    - OpenMVS surface tuning: -f 1, --remove-spurious 20, --remove-spikes 1, --close-holes 30, --smooth 2.
    - Python garbage filtering: drops triangles with edge length > 6x median and faces outside expanded camera bounding box.
    - Nearest-neighbor vertex color transfer from dense point cloud.
    - Camera mean up-vector alignment (up = +Y) for preview_mesh.glb and preview_cloud.ply.
    """
    name: str = "openmvs_reconstruct_mesh"
    weight: float = 2.0
    declared_outputs: List[str] = [
        "scene_dense_mesh.ply",
        "scene_dense_mesh.mvs",
        "raw_mesh.ply",
        "raw_mesh.glb",
        "preview_mesh.glb",
        "preview_cloud.ply",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Initializing Delaunay tetrahedral surface mesh reconstruction (ReconstructMesh)...")
        rmesh_bin = resolve_openmvs("ReconstructMesh")
        threads = str(get_configured_threads())

        input_mvs = ctx.workdir / "scene_dense.mvs"
        output_ply = ctx.workdir / "scene_dense_mesh.ply"
        output_mvs = ctx.workdir / "scene_dense_mesh.mvs"

        if not input_mvs.exists():
            raise FileNotFoundError(f"Dense scene input not found: {input_mvs}")

        # ReconstructMesh with tuned parameters
        cmd = [
            rmesh_bin,
            "-w", str(ctx.workdir),
            "-i", "scene_dense.mvs",
            "-o", "scene_dense_mesh.mvs",
            "--max-threads", threads,
            "-f", "1",
            "--remove-spurious", "20",
            "--remove-spikes", "1",
            "--close-holes", "30",
            "--smooth", "2",
            "-v", "2",
        ]

        ctx.log_cb(f"[OpenMVS] Running ReconstructMesh -> {output_mvs.name} (threads: {threads}, free-space: 1, smooth: 2)...")
        res = ToolRunner.run(
            cmd,
            cwd=str(ctx.workdir),
            log_callback=ctx.log_cb,
            cancel_token=ctx.cancel_token,
            timeout=1200,
        )

        if not output_ply.exists():
            raise RuntimeError(
                f"ReconstructMesh completed with exit code {res.exit_code} "
                f"but output {output_ply} was not created."
            )

        # Parse camera poses, bounding box, and up vector
        mean_up, cam_min, cam_max, R_align = parse_camera_poses_and_up_vector(ctx.workdir)
        if mean_up is not None:
            ctx.log_cb(
                f"[OpenMVS] Camera trajectory orientation: mean_up=[{mean_up[0]:.3f}, {mean_up[1]:.3f}, {mean_up[2]:.3f}], "
                f"cam_bounds=([{cam_min[0]:.2f}, {cam_min[1]:.2f}, {cam_min[2]:.2f}] to [{cam_max[0]:.2f}, {cam_max[1]:.2f}, {cam_max[2]:.2f}])"
            )

        # Load mesh for Python-side garbage filtering and vertex color transfer
        import trimesh
        mesh = trimesh.load(str(output_ply), process=False)
        if isinstance(mesh, trimesh.Scene):
            mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))

        orig_verts = len(mesh.vertices)
        orig_faces = len(mesh.faces)
        ctx.log_cb(f"[OpenMVS] Raw mesh loaded: {orig_verts:,} vertices, {orig_faces:,} faces.")

        # 1. Edge length filter: drop triangles with max edge length > 6.0 * median
        face_v = mesh.vertices[mesh.faces]
        e0 = np.linalg.norm(face_v[:, 1] - face_v[:, 0], axis=1)
        e1 = np.linalg.norm(face_v[:, 2] - face_v[:, 1], axis=1)
        e2 = np.linalg.norm(face_v[:, 0] - face_v[:, 2], axis=1)
        max_face_edges = np.maximum(np.maximum(e0, e1), e2)
        med_edge = float(np.median(max_face_edges))
        max_edge_thresh = 6.0 * med_edge
        valid_edge_mask = max_face_edges <= max_edge_thresh
        dropped_edges = int(np.sum(~valid_edge_mask))

        # 2. Camera bounding box filter: drop faces outside expanded camera box
        # Ensure minimum margin along all axes (e.g. at least 2.5m / 0.4*max_span) for planar/tripod trajectories
        dropped_bbox = 0
        in_box_mask = np.ones(len(mesh.faces), dtype=bool)
        if cam_min is not None and cam_max is not None:
            cam_span = cam_max - cam_min
            max_span = float(np.max(cam_span))
            margin = np.maximum(1.2 * cam_span, max(0.4 * max_span, 2.5))
            box_min = cam_min - margin
            box_max = cam_max + margin
            face_centers = np.mean(face_v, axis=1)
            in_box_mask = np.all((face_centers >= box_min) & (face_centers <= box_max), axis=1)
            dropped_bbox = int(np.sum(~in_box_mask))

        keep_faces = valid_edge_mask & in_box_mask
        mesh.update_faces(keep_faces)
        mesh.remove_unreferenced_vertices()

        ctx.log_cb(
            f"[OpenMVS] Mesh cleaning: dropped {dropped_edges:,} long-edge faces (> {max_edge_thresh:.3f}) "
            f"and {dropped_bbox:,} out-of-bounds faces (bounding box: [{box_min[0]:.1f}, {box_min[1]:.1f}, {box_min[2]:.1f}] to [{box_max[0]:.1f}, {box_max[1]:.1f}, {box_max[2]:.1f}])."
        )
        ctx.log_cb(f"[OpenMVS] Cleaned mesh: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces (kept {len(mesh.faces)/max(1, orig_faces)*100:.1f}%).")

        # 3. Nearest-neighbor vertex color transfer from scene_dense.ply
        dense_ply = ctx.workdir / "scene_dense.ply"
        if dense_ply.exists():
            try:
                import open3d as o3d
                pcd = o3d.io.read_point_cloud(str(dense_ply))
                if len(pcd.points) > 0 and pcd.has_colors():
                    pcd_tree = o3d.geometry.KDTreeFlann(pcd)
                    mesh_verts = np.asarray(mesh.vertices)
                    pcd_colors = (np.asarray(pcd.colors) * 255).astype(np.uint8)
                    vert_colors = np.zeros((len(mesh_verts), 4), dtype=np.uint8)
                    vert_colors[:, 3] = 255
                    for i in range(len(mesh_verts)):
                        [_, idx, _] = pcd_tree.search_knn_vector_3d(mesh_verts[i], 1)
                        vert_colors[i, :3] = pcd_colors[idx[0]]
                    mesh.visual.vertex_colors = vert_colors
                    ctx.log_cb(f"[OpenMVS] Vertex colors transferred via KDTree from dense cloud ({len(pcd.points):,} points).")
            except Exception as e:
                ctx.log_cb(f"[OpenMVS] Warning: Color transfer from dense cloud encountered: {e}")

        # Save cleaned unoriented raw meshes
        raw_ply = ctx.workdir / "raw_mesh.ply"
        raw_glb = ctx.workdir / "raw_mesh.glb"
        mesh.export(str(raw_ply))
        mesh.export(str(raw_glb))

        # Save oriented preview mesh (up = +Y)
        preview_glb = ctx.workdir / "preview_mesh.glb"
        preview_mesh = mesh.copy()
        preview_mesh.vertices = (R_align @ preview_mesh.vertices.T).T
        preview_mesh.export(str(preview_glb))
        ctx.log_cb(f"[OpenMVS] Oriented preview mesh exported: {preview_glb.name} (up = +Y, {len(preview_mesh.vertices):,} vertices).")

        # Save oriented preview point cloud (up = +Y)
        preview_cloud = ctx.workdir / "preview_cloud.ply"
        if dense_ply.exists():
            try:
                import open3d as o3d
                pcd = o3d.io.read_point_cloud(str(dense_ply))
                pcd.rotate(R_align, center=(0, 0, 0))
                o3d.io.write_point_cloud(str(preview_cloud), pcd)
                ctx.log_cb(f"[OpenMVS] Oriented preview point cloud exported: {preview_cloud.name} (up = +Y).")
            except Exception as e:
                ctx.log_cb(f"[OpenMVS] Warning: Failed to export oriented point cloud: {e}")

        outputs = [output_ply, raw_ply, raw_glb, preview_glb]
        if output_mvs.exists():
            outputs.append(output_mvs)
        if preview_cloud.exists():
            outputs.append(preview_cloud)

        return StageResult(
            success=True,
            output_files=outputs,
            metadata={
                "vertex_count": len(mesh.vertices),
                "face_count": len(mesh.faces),
                "dropped_long_edge_faces": dropped_edges,
                "dropped_bbox_faces": dropped_bbox,
                "raw_ply": str(raw_ply.name),
                "raw_glb": str(raw_glb.name),
                "preview_glb": str(preview_glb.name),
                "preview_cloud": str(preview_cloud.name) if preview_cloud.exists() else None,
            },
        )


class OpenMVSTextureStage(Stage):
    """
    Applies photographic UV texture mapping to the mesh using OpenMVS TextureMesh.
    Creates scene_textured.glb, scene_textured.png (texture atlas), and
    oriented preview_textured.glb (up = +Y).
    """
    name: str = "openmvs_texture"
    weight: float = 2.5
    declared_outputs: List[str] = [
        "scene_textured.glb",
        "scene_textured.png",
        "preview_textured.glb",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Initializing photographic UV texture mapping (TextureMesh)...")
        texture_bin = resolve_openmvs("TextureMesh")
        threads = str(get_configured_threads())

        input_mvs = ctx.workdir / "scene_dense_mesh.mvs"
        if not input_mvs.exists():
            raise FileNotFoundError(f"Input mesh project not found: {input_mvs}. Ensure OpenMVSRMeshStage ran.")

        output_glb = ctx.workdir / "scene_textured.glb"
        cmd = [
            texture_bin,
            "-w", str(ctx.workdir),
            "-i", "scene_dense_mesh.mvs",
            "-o", "scene_textured.glb",
            "--export-type", "glb",
            "--resolution-level", "1",
            "--max-threads", threads,
            "-v", "2",
        ]

        ctx.log_cb(f"[OpenMVS] Running TextureMesh -> {output_glb.name} (resolution-level 1, threads: {threads})...")
        res = ToolRunner.run(
            cmd,
            cwd=str(ctx.workdir),
            log_callback=ctx.log_cb,
            cancel_token=ctx.cancel_token,
            timeout=2400,
        )

        if not output_glb.exists():
            raise RuntimeError(
                f"TextureMesh completed with exit code {res.exit_code} "
                f"but output {output_glb} was not created."
            )

        texture_png = ctx.workdir / "scene_textured.png"
        preview_textured_glb = ctx.workdir / "preview_textured.glb"

        # Orient textured mesh so up = +Y
        try:
            _, _, _, R_align = parse_camera_poses_and_up_vector(ctx.workdir)
            import trimesh
            scene = trimesh.load(str(output_glb))
            T = np.eye(4)
            T[:3, :3] = R_align
            scene.apply_transform(T)
            scene.export(str(preview_textured_glb))
            ctx.log_cb(f"[OpenMVS] Oriented textured preview exported: {preview_textured_glb.name} (up = +Y).")
        except Exception as e:
            ctx.log_cb(f"[OpenMVS] Warning: Failed to orient textured GLB: {e}")

        outputs = [output_glb]
        if texture_png.exists():
            outputs.append(texture_png)
        if preview_textured_glb.exists():
            outputs.append(preview_textured_glb)

        ctx.log_cb(
            f"[OpenMVS] Textured mesh completed: {output_glb.name} ({output_glb.stat().st_size / (1024*1024):.2f} MB)"
        )

        return StageResult(
            success=True,
            output_files=outputs,
            metadata={
                "textured_glb": str(output_glb.name),
                "preview_textured_glb": str(preview_textured_glb.name) if preview_textured_glb.exists() else None,
                "texture_png": str(texture_png.name) if texture_png.exists() else None,
            },
        )
