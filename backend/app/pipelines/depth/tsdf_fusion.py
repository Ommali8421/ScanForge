"""
TSDF Fusion Stage (Milestone P4 Route B)
Integrates aligned RGB-D video frames into an Open3D ScalableTSDFVolume
using scale-invariant voxel sizing:
  - If calibrated: 0.03m (standard) / 0.02m (high) / 0.05m (draft)
  - If uncalibrated: D_room / 380 (standard) / D_room / 520 (high) / D_room / 250 (draft)
Extracts watertight / surface mesh (mesh_tsdf_raw.ply) for downstream plane-aware post-processing.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
import cv2
import numpy as np

from app.config import settings
from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.depth.depth_align import parse_colmap_sparse, find_colmap_sparse_dir
from app.utils.logging import logger


class TSDFFusionStage(Stage):
    """
    Volumetric TSDF fusion of registered RGB images and aligned depth maps.
    Outputs mesh_tsdf_raw.ply (and mesh_dense.ply) for downstream processing.
    """
    name: str = "tsdf_fusion"
    weight: float = 4.0
    declared_outputs: List[str] = ["mesh_tsdf_raw.ply", "mesh_dense.ply"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[TSDFFusion] Initializing volumetric TSDF depth fusion...")
        depth_aligned_dir = ctx.workdir / "depth_aligned"
        frames_dir = ctx.workdir / "frames"

        # Skip for Route A (photogrammetry) — OpenMVS provides the mesh directly
        decision_file = ctx.workdir / "mesh_route_decision.json"
        if decision_file.exists():
            try:
                dec = json.loads(decision_file.read_text()).get("decision", "")
                if dec == "photogrammetry":
                    ctx.log_cb("[TSDFFusion] Route A (Photogrammetry) active. Skipping TSDF fusion.")
                    return StageResult(success=True, skipped_cache=True)
            except Exception:
                pass

        is_mock = (settings.SCANFORGE_ENGINE == "mock") or (ctx.params.get("options", {}).get("engine") == "mock")
        out_mesh_path = ctx.workdir / "mesh_tsdf_raw.ply"
        mesh_dense_path = ctx.workdir / "mesh_dense.ply"

        if is_mock:
            ctx.log_cb("[TSDFFusion] MOCK engine active: generating procedural room mesh...")
            import trimesh
            box = trimesh.creation.box(extents=[6.0, 3.0, 5.0])
            box.export(str(out_mesh_path))
            box.export(str(mesh_dense_path))
            return StageResult(
                success=True,
                output_files=[out_mesh_path, mesh_dense_path],
                metadata={"vertex_count": len(box.vertices), "face_count": len(box.faces)}
            )

        import open3d as o3d

        sparse_dir = find_colmap_sparse_dir(ctx.workdir)
        cams, images, points3d = parse_colmap_sparse(sparse_dir)
        if len(images) == 0:
            raise RuntimeError(f"[TSDFFusion] No registered images found in COLMAP model at {sparse_dir}")
        ctx.log_cb(f"[TSDFFusion] Loaded camera poses for {len(images)} images from {sparse_dir.name}.")

        # Determine scale-invariant room bounds and center
        if points3d:
            pts_array = np.array(list(points3d.values()), dtype=np.float32)
            p_min = np.percentile(pts_array, 2.0, axis=0)
            p_max = np.percentile(pts_array, 98.0, axis=0)
            p_center = 0.5 * (p_min + p_max)
            d_room = float(np.linalg.norm(p_max - p_min))
        else:
            p_center = np.zeros(3, dtype=np.float32)
            d_room = 10.0

        quality = ctx.params.get("quality", "standard").lower()
        is_calibrated = bool(ctx.params.get("is_calibrated", False))

        # Dynamic bounding cube size and resolution
        vol_len = max(d_room * 1.5, 4.0)
        vol_origin = p_center - vol_len / 2.0

        if quality == "high":
            resolution = 448  # Capped at 448 to prevent host RAM pressure in WSL2
        elif quality == "draft":
            resolution = 256
        else:
            resolution = 384

        voxel_size = vol_len / float(resolution)
        # Amendment 3: Increase sdf_trunc to 8.0 * voxel_size
        sdf_trunc = max(8.0 * voxel_size, 0.05)

        ctx.log_cb(
            f"[TSDFFusion] Room center=[{p_center[0]:.2f}, {p_center[1]:.2f}, {p_center[2]:.2f}], D_room={d_room:.2f}. "
            f"UniformTSDFVolume len={vol_len:.2f}, res={resolution}, voxel_size={voxel_size:.4f}, sdf_trunc={sdf_trunc:.4f}."
        )

        volume = o3d.pipelines.integration.UniformTSDFVolume(
            length=vol_len,
            resolution=resolution,
            sdf_trunc=sdf_trunc,
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
            origin=vol_origin.astype(np.float64),
        )

        t0 = time.time()
        integrated_count = 0

        for idx, img in enumerate(images):
            stem = Path(img["name"]).stem
            depth_file = depth_aligned_dir / f"{stem}.npy"
            color_file = frames_dir / img["name"]

            if not depth_file.exists() or not color_file.exists():
                continue

            depth_np = np.load(str(depth_file)).astype(np.float32)

            # 1-pixel finite difference relative step discontinuity check (replaces 8x Sobel scaling bug)
            # Only mask true occlusion jumps where relative step > 12% in a SINGLE pixel, leaving smooth floors/walls intact
            dz_dx = np.abs(np.diff(depth_np, axis=1, prepend=depth_np[:, :1]))
            dz_dy = np.abs(np.diff(depth_np, axis=0, prepend=depth_np[:1, :]))
            step_rel = np.maximum(dz_dx, dz_dy) / np.maximum(depth_np, 1e-4)
            edge_mask = step_rel > 0.12
            depth_np[edge_mask] = 0.0

            color_bgr = cv2.imread(str(color_file))
            if color_bgr is None:
                continue

            color_rgb = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)
            h, w = depth_np.shape[:2]

            # Resize color if dimensions mismatch depth
            if color_rgb.shape[0] != h or color_rgb.shape[1] != w:
                color_rgb = cv2.resize(color_rgb, (w, h), interpolation=cv2.INTER_LINEAR)

            # Create Open3D RGBD Image
            o3d_color = o3d.geometry.Image(color_rgb)
            o3d_depth = o3d.geometry.Image(depth_np)

            max_depth = float(np.percentile(depth_np, 98.0)) * 1.15
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d_color,
                o3d_depth,
                depth_scale=1.0,  # Depth is already in floating-point meters / units
                depth_trunc=max_depth,
                convert_rgb_to_intensity=False,
            )

            # Camera intrinsics
            cam_info = cams.get(img["cam_id"], {"fx": 1000.0, "fy": 1000.0, "cx": w/2.0, "cy": h/2.0})
            fx = float(cam_info["fx"]) * (w / float(cam_info.get("w", w)))
            fy = float(cam_info["fy"]) * (h / float(cam_info.get("h", h)))
            cx = float(cam_info["cx"]) * (w / float(cam_info.get("w", w)))
            cy = float(cam_info["cy"]) * (h / float(cam_info.get("h", h)))

            intrinsic = o3d.camera.PinholeCameraIntrinsic(w, h, fx, fy, cx, cy)

            # Extrinsics [R | t] (world to camera)
            extrinsic = np.eye(4, dtype=np.float64)
            extrinsic[:3, :3] = img["R"]
            extrinsic[:3, 3] = img["t"]

            volume.integrate(rgbd, intrinsic, extrinsic)
            integrated_count += 1

            if (idx + 1) % 25 == 0 or (idx + 1) == len(images):
                ctx.log_cb(f"[TSDFFusion] Integrated {idx+1}/{len(images)} RGB-D frames...")

        ctx.log_cb(f"[TSDFFusion] Finished integrating {integrated_count} frames in {time.time()-t0:.1f}s. Extracting triangle mesh...")
        mesh = volume.extract_triangle_mesh()
        num_verts = len(mesh.vertices)
        num_faces = len(mesh.triangles)

        ctx.log_cb(f"[TSDFFusion] Extracted raw TSDF mesh with {num_verts:,} vertices and {num_faces:,} triangles.")

        if num_verts == 0 or num_faces == 0:
            raise RuntimeError("[TSDFFusion] Extracted TSDF mesh has 0 vertices or 0 faces.")

        # Amendment 3: C++ Taubin smoothing on raw TSDF mesh to damp surface ripple
        ctx.log_cb("[TSDFFusion] Applying 10 iterations of C++ Taubin surface smoothing...")
        mesh = mesh.filter_smooth_taubin(number_of_iterations=10)
        mesh.compute_vertex_normals()

        # Amendment 3: Prune disconnected internal floating sheets (< 2,500 faces or < 3% main cluster)
        ctx.log_cb("[TSDFFusion] Pruning disconnected noise sheets and internal curtains...")
        triangle_clusters, cluster_n_triangles, _ = mesh.cluster_connected_triangles()
        cluster_n_triangles = np.asarray(cluster_n_triangles)
        max_cluster_faces = int(np.max(cluster_n_triangles)) if len(cluster_n_triangles) > 0 else 0
        min_cluster_faces = max(2500, int(0.03 * max_cluster_faces))
        triangles_to_keep = cluster_n_triangles[np.asarray(triangle_clusters)] >= min_cluster_faces
        mesh.remove_triangles_by_mask(~triangles_to_keep)
        mesh.remove_unreferenced_vertices()
        mesh.compute_vertex_normals()

        final_verts = len(mesh.vertices)
        final_faces = len(mesh.triangles)
        ctx.log_cb(f"[TSDFFusion] Cleaned TSDF mesh: {final_verts:,} vertices, {final_faces:,} triangles.")

        # Save primary raw TSDF mesh and copy to mesh_dense.ply for downstream stages
        o3d.io.write_triangle_mesh(str(out_mesh_path), mesh, write_vertex_normals=True, write_vertex_colors=True)
        o3d.io.write_triangle_mesh(str(mesh_dense_path), mesh, write_vertex_normals=True, write_vertex_colors=True)

        return StageResult(
            success=True,
            output_files=[out_mesh_path, mesh_dense_path],
            metadata={
                "vertex_count": final_verts,
                "face_count": final_faces,
                "integrated_frames": integrated_count,
                "voxel_size": round(voxel_size, 5),
            }
        )
