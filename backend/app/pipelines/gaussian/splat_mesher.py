"""
Splat Mesher Stage (Milestone P4 Mesh-Inclusive 3DGS)
Renders expected depth and alpha directly from trained upright Y=0 3D Gaussians
using gsplat.rasterization (render_mode="RGB+ED"), masks low-alpha void pixels (< 0.5),
and fuses into Open3D ScalableTSDFVolume.
Produces mesh_splat_raw.ply and mesh_dense.ply for downstream plane repair and texturing.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
import cv2
import numpy as np
from plyfile import PlyData

from app.config import settings
from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.depth.depth_align import parse_colmap_sparse, find_colmap_sparse_dir
from app.utils.logging import logger


class SplatMesherStage(Stage):
    """
    Renders expected depth and alpha from trained 3D Gaussians across registered cameras,
    and fuses them into a watertight mesh via ScalableTSDFVolume.
    """
    name: str = "splat_mesher"
    weight: float = 4.5
    declared_outputs: List[str] = ["mesh_splat_raw.ply", "mesh_dense.ply"]

    def run(self, ctx: JobContext) -> StageResult:
        # Check if mesh inclusion is requested
        include_mesh = bool(ctx.params.get("options", {}).get("include_mesh", False))
        if not include_mesh:
            ctx.log_cb("[SplatMesher] 'include_mesh' is False. Skipping splat meshing stage.")
            return StageResult(success=True, skipped_cache=True)

        ctx.log_cb("[SplatMesher] Initializing 3DGS splat-rendered depth extraction and TSDF meshing...")
        out_mesh_path = ctx.workdir / "mesh_splat_raw.ply"
        mesh_dense_path = ctx.workdir / "mesh_dense.ply"

        is_mock = (settings.SCANFORGE_ENGINE == "mock") or (ctx.params.get("options", {}).get("engine") == "mock")
        if is_mock:
            ctx.log_cb("[SplatMesher] MOCK engine active: generating procedural splat mesh...")
            import trimesh
            box = trimesh.creation.box(extents=[7.0, 3.2, 5.5])
            box.export(str(out_mesh_path))
            box.export(str(mesh_dense_path))
            return StageResult(
                success=True,
                output_files=[out_mesh_path, mesh_dense_path],
                metadata={"vertex_count": len(box.vertices), "face_count": len(box.faces)}
            )

        import torch
        import gsplat
        import open3d as o3d

        input_ply = ctx.workdir / "cleaned_splat.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "model.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "splat.ply"
        if not input_ply.exists():
            raise FileNotFoundError(f"[SplatMesher] Cleaned 3DGS PLY not found in {ctx.workdir}")

        sparse_dir = find_colmap_sparse_dir(ctx.workdir)
        cams, images, points3d = parse_colmap_sparse(sparse_dir)
        ctx.log_cb(f"[SplatMesher] Loaded {len(images)} registered camera poses from {sparse_dir.name}.")

        # Load 3D Gaussians into PyTorch CUDA tensors
        ctx.log_cb(f"[SplatMesher] Loading Gaussians from {input_ply.name}...")
        ply = PlyData.read(str(input_ply))["vertex"]
        pts = np.column_stack([ply["x"], ply["y"], ply["z"]]).astype(np.float32)
        num_gaussians = len(pts)

        means = torch.tensor(pts, dtype=torch.float32, device="cuda")
        quats = torch.tensor(
            np.column_stack([ply["rot_0"], ply["rot_1"], ply["rot_2"], ply["rot_3"]]),
            dtype=torch.float32, device="cuda"
        )
        quats = torch.nn.functional.normalize(quats, p=2, dim=-1)

        s0 = np.exp(np.clip(np.asarray(ply["scale_0"]), -20.0, 5.0))
        s1 = np.exp(np.clip(np.asarray(ply["scale_1"]), -20.0, 5.0))
        s2 = np.exp(np.clip(np.asarray(ply["scale_2"]), -20.0, 5.0))
        scales = torch.tensor(np.column_stack([s0, s1, s2]), dtype=torch.float32, device="cuda")

        opacities_raw = np.asarray(ply["opacity"], dtype=np.float32)
        opacities = torch.tensor(
            1.0 / (1.0 + np.exp(-np.clip(opacities_raw, -20.0, 20.0))),
            dtype=torch.float32, device="cuda"
        )

        C0 = 0.28209479177387814
        sh_0 = torch.tensor(
            np.column_stack([ply["f_dc_0"], ply["f_dc_1"], ply["f_dc_2"]]),
            dtype=torch.float32, device="cuda"
        )
        colors = torch.clamp(0.5 + C0 * sh_0, 0.0, 1.0)

        # Scale-invariant room extent and dynamic bounding cube
        p_min = np.percentile(pts, 2.0, axis=0)
        p_max = np.percentile(pts, 98.0, axis=0)
        p_center = 0.5 * (p_min + p_max)
        d_room = float(np.linalg.norm(p_max - p_min))

        quality = ctx.params.get("quality", "standard").lower()
        vol_len = max(d_room * 1.5, 4.0)
        vol_origin = p_center - vol_len / 2.0
        resolution = 448 if quality == "high" else (256 if quality == "draft" else 384)  # Capped at <=448 for WSL2 RAM safety
        voxel_size = vol_len / float(resolution)
        sdf_trunc = max(5.0 * voxel_size, 0.05)

        ctx.log_cb(
            f"[SplatMesher] D_room={d_room:.2f} units, center=[{p_center[0]:.2f}, {p_center[1]:.2f}, {p_center[2]:.2f}]. "
            f"UniformTSDFVolume len={vol_len:.2f}, res={resolution}, voxel_size={voxel_size:.4f}, sdf_trunc={sdf_trunc:.4f}..."
        )

        volume = o3d.pipelines.integration.UniformTSDFVolume(
            length=vol_len,
            resolution=resolution,
            sdf_trunc=sdf_trunc,
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
            origin=vol_origin.astype(np.float64),
        )

        # Render depth + RGB across registered cameras
        render_w, render_h = 960, 540  # Memory-safe resolution for TSDF fusion
        t0 = time.time()
        fused_views = 0

        # Load cameras_aligned.json if available for centered coordinates
        aligned_cam_map = {}
        cam_json_file = ctx.workdir / "cameras_aligned.json"
        if cam_json_file.exists():
            try:
                cdata = json.loads(cam_json_file.read_text())
                for c in cdata.get("cameras", []):
                    aligned_cam_map[c["name"]] = c
            except Exception:
                pass

        with torch.no_grad():
            for idx, img in enumerate(images):
                img_name = img["name"]
                cam_info = cams.get(img["cam_id"], {"fx": 1000.0, "fy": 1000.0, "cx": render_w/2.0, "cy": render_h/2.0})

                orig_w = float(cam_info.get("w", render_w))
                orig_h = float(cam_info.get("h", render_h))
                sx = render_w / orig_w
                sy = render_h / orig_h

                fx = float(cam_info["fx"]) * sx
                fy = float(cam_info["fy"]) * sy
                cx = float(cam_info["cx"]) * sx
                cy = float(cam_info["cy"]) * sy

                K = torch.tensor([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]], dtype=torch.float32, device="cuda").unsqueeze(0)

                # World to camera matrix
                w2c = np.eye(4, dtype=np.float32)
                if img_name in aligned_cam_map:
                    # Construct w2c from aligned camera position and up/fwd vectors
                    ac = aligned_cam_map[img_name]
                    pos = np.array(ac["position"], dtype=float)
                    fwd = np.array(ac.get("forward", [0.0, 0.0, 1.0]), dtype=float)
                    up_vec = np.array(ac.get("up", [0.0, 1.0, 0.0]), dtype=float)
                    lookat = pos + fwd

                    z_c = (lookat - pos) / max(np.linalg.norm(lookat - pos), 1e-6)
                    x_c = np.cross(z_c, up_vec)
                    x_c = x_c / max(np.linalg.norm(x_c), 1e-6)
                    y_c = np.cross(z_c, x_c)
                    y_c = y_c / max(np.linalg.norm(y_c), 1e-6)
                    R_c = np.vstack([x_c, y_c, z_c])
                    t_c = -R_c @ pos
                    w2c[:3, :3] = R_c
                    w2c[:3, 3] = t_c
                else:
                    w2c[:3, :3] = img["R"]
                    w2c[:3, 3] = img["t"]

                viewmats = torch.tensor(w2c, dtype=torch.float32, device="cuda").unsqueeze(0)

                # Render expected depth + colors with gsplat
                render_colors, render_alphas, meta = gsplat.rasterization(
                    means=means,
                    quats=quats,
                    scales=scales,
                    opacities=opacities,
                    colors=colors,
                    viewmats=viewmats,
                    Ks=K,
                    width=render_w,
                    height=render_h,
                    near_plane=0.01,
                    far_plane=1e6,
                    render_mode="RGB+ED",
                )

                # Split RGB and Expected Depth
                # render_colors has shape [1, H, W, 4] where [..., 0:3] is RGB and [..., 3] is Expected Depth
                out_rgb = torch.clamp(render_colors[0, ..., :3], 0.0, 1.0).cpu().numpy()
                out_depth = render_colors[0, ..., 3].cpu().numpy()
                out_alpha = render_alphas[0, ..., 0].cpu().numpy()

                # Mask low-alpha void regions (< 0.50)
                valid_mask = out_alpha >= 0.50
                out_depth[~valid_mask] = 0.0

                rgb_uint8 = (out_rgb * 255.0).astype(np.uint8)
                depth_f32 = out_depth.astype(np.float32)

                # Integrate into TSDF
                o3d_color = o3d.geometry.Image(rgb_uint8)
                o3d_depth = o3d.geometry.Image(depth_f32)
                intrinsic_o3d = o3d.camera.PinholeCameraIntrinsic(render_w, render_h, fx, fy, cx, cy)

                extrinsic_o3d = np.eye(4, dtype=np.float64)
                extrinsic_o3d[:3, :3] = w2c[:3, :3]
                extrinsic_o3d[:3, 3] = w2c[:3, 3]

                rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                    o3d_color,
                    o3d_depth,
                    depth_scale=1.0,
                    depth_trunc=float(np.percentile(depth_f32[valid_mask], 98.0)) * 1.10 if np.any(valid_mask) else 20.0,
                    convert_rgb_to_intensity=False,
                )

                volume.integrate(rgbd, intrinsic_o3d, extrinsic_o3d)
                fused_views += 1

                if (idx + 1) % 25 == 0 or (idx + 1) == len(images):
                    ctx.log_cb(f"[SplatMesher] Rendered & integrated {idx+1}/{len(images)} splat views...")

        # Purge GPU tensors immediately
        del means, quats, scales, opacities, colors
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        ctx.log_cb(f"[SplatMesher] Finished rendering in {time.time()-t0:.1f}s. Extracting triangle mesh...")
        mesh = volume.extract_triangle_mesh()
        mesh.compute_vertex_normals()

        # Remove disconnected clusters
        triangle_clusters, cluster_n_triangles, _ = mesh.cluster_connected_triangles()
        cluster_n_triangles = np.asarray(cluster_n_triangles)
        triangles_to_keep = cluster_n_triangles[np.asarray(triangle_clusters)] >= 150
        mesh.remove_triangles_by_mask(~triangles_to_keep)
        mesh.remove_unreferenced_vertices()

        num_verts = len(mesh.vertices)
        num_faces = len(mesh.triangles)
        ctx.log_cb(f"[SplatMesher] Extracted mesh-inclusive mesh: {num_verts:,} vertices, {num_faces:,} faces.")

        o3d.io.write_triangle_mesh(str(out_mesh_path), mesh, write_vertex_normals=True, write_vertex_colors=True)
        o3d.io.write_triangle_mesh(str(mesh_dense_path), mesh, write_vertex_normals=True, write_vertex_colors=True)

        return StageResult(
            success=True,
            output_files=[out_mesh_path, mesh_dense_path],
            metadata={
                "vertex_count": num_verts,
                "face_count": num_faces,
                "fused_views": fused_views,
            }
        )
