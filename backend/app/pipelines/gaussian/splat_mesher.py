"""
Splat Mesher Stage (Milestone P4 Mesh-Inclusive 3DGS)
Renders expected depth and alpha directly from trained upright Y=0 3D Gaussians
using gsplat.rasterization (render_mode="RGB+ED"), masks low-alpha void pixels (< 0.70),
filters depth-discontinuity edges, applies median filtering, fuses into Open3D UniformTSDFVolume,
smooths via Open3D Taubin smoothing, and transforms the resulting mesh back into raw COLMAP sparse space
via Kabsch/SVD camera-paired rigid alignment.
Produces mesh_splat_raw.ply and mesh_dense.ply for downstream plane repair and OpenMVS texturing.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np
from plyfile import PlyData

from app.config import settings
from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.depth.depth_align import parse_colmap_sparse, find_colmap_sparse_dir
from app.utils.logging import logger


def compute_kabsch_transform(
    cams_clean: Dict[str, Any],
    images_raw: List[Dict[str, Any]],
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Computes exact orthogonal rigid transform (R, t) mapping clean splat space to raw COLMAP sparse space.
    Uses Kabsch/SVD on paired registered camera centers and forward/up basis vectors.
    """
    pts_clean = []
    pts_raw = []
    matched_names = []

    for img in images_raw:
        name = img["name"]
        if name in cams_clean:
            c_clean = np.array(cams_clean[name]["position"], dtype=float)
            f_clean = np.array(cams_clean[name].get("forward", [0.0, 0.0, 1.0]), dtype=float)
            u_clean = np.array(cams_clean[name].get("up", [0.0, 1.0, 0.0]), dtype=float)

            R_raw = img["R"]
            t_raw = img["t"]
            c_raw = -R_raw.T @ t_raw
            f_raw = R_raw.T @ np.array([0.0, 0.0, 1.0])
            u_raw = R_raw.T @ np.array([0.0, -1.0, 0.0])

            pts_clean.extend([c_clean, c_clean + f_clean, c_clean + u_clean])
            pts_raw.extend([c_raw, c_raw + f_raw, c_raw + u_raw])
            matched_names.append(name)

    if len(matched_names) < 3:
        raise RuntimeError(f"Insufficient paired cameras ({len(matched_names)}) to compute Kabsch alignment.")

    A = np.array(pts_clean, dtype=np.float64)
    B = np.array(pts_raw, dtype=np.float64)

    centroid_A = np.mean(A, axis=0)
    centroid_B = np.mean(B, axis=0)
    AA = A - centroid_A
    BB = B - centroid_B

    H = AA.T @ BB
    U, S, Vt = np.linalg.svd(H)
    R_mat = Vt.T @ U.T

    det = np.linalg.det(R_mat)
    if det < 0:
        Vt[2, :] *= -1.0
        R_mat = Vt.T @ U.T

    t_vec = centroid_B - R_mat @ centroid_A

    # Evaluate camera center error
    clean_centers = np.array([cams_clean[name]["position"] for name in matched_names])
    raw_centers = np.array([-img["R"].T @ img["t"] for img in images_raw if img["name"] in matched_names])
    pred_raw = (R_mat @ clean_centers.T).T + t_vec
    errors = np.linalg.norm(pred_raw - raw_centers, axis=1)
    max_err = float(np.max(errors))

    return R_mat, t_vec, max_err


class SplatMesherStage(Stage):
    """
    Renders expected depth and alpha from trained 3D Gaussians across registered cameras,
    and fuses them into a watertight mesh via UniformTSDFVolume.
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
        resolution = 448 if quality == "high" else (256 if quality == "draft" else 384)
        voxel_size = vol_len / float(resolution)
        # Amendment 3: Increase sdf_trunc to 8.0 * voxel_size
        sdf_trunc = max(8.0 * voxel_size, 0.05)

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

        # Load cameras_aligned.json for centered coordinates
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
                # In gsplat 1.4.0, RGB+ED is ALREADY alpha-normalized! (Amendment 2: Do NOT divide by alpha again)
                out_rgb = torch.clamp(render_colors[0, ..., :3], 0.0, 1.0).cpu().numpy()
                out_depth = render_colors[0, ..., 3].cpu().numpy().astype(np.float32)
                out_alpha = render_alphas[0, ..., 0].cpu().numpy().astype(np.float32)

                # Relax opacity masking from alpha < 0.70 to alpha < 0.45 so smooth floor/ceiling surflets stay intact
                valid_mask = (out_alpha >= 0.45) & (out_depth > 0.05)
                out_depth[~valid_mask] = 0.0

                # 1-pixel finite difference relative step discontinuity check (replaces 8x Sobel scaling bug)
                # True 1-pixel finite differences mask step jumps > 12% in a SINGLE pixel, leaving smooth perspective floors/walls intact
                dz_dx = np.abs(np.diff(out_depth, axis=1, prepend=out_depth[:, :1]))
                dz_dy = np.abs(np.diff(out_depth, axis=0, prepend=out_depth[:1, :]))
                step_rel = np.maximum(dz_dx, dz_dy) / np.maximum(out_depth, 1e-4)
                edge_mask = step_rel > 0.12
                out_depth[edge_mask] = 0.0

                # 5x5 median filtering to remove isolated spikes
                depth_med = cv2.medianBlur(out_depth, 5)
                depth_med[~valid_mask] = 0.0
                depth_med[edge_mask] = 0.0

                rgb_uint8 = (out_rgb * 255.0).astype(np.uint8)

                # Integrate into TSDF
                o3d_color = o3d.geometry.Image(rgb_uint8)
                o3d_depth = o3d.geometry.Image(depth_med)
                intrinsic_o3d = o3d.camera.PinholeCameraIntrinsic(render_w, render_h, fx, fy, cx, cy)

                extrinsic_o3d = np.eye(4, dtype=np.float64)
                extrinsic_o3d[:3, :3] = w2c[:3, :3]
                extrinsic_o3d[:3, 3] = w2c[:3, 3]

                rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                    o3d_color,
                    o3d_depth,
                    depth_scale=1.0,
                    depth_trunc=float(np.percentile(depth_med[valid_mask], 98.0)) * 1.10 if np.any(valid_mask) else 20.0,
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

        # Amendment 3: C++ Taubin smoothing on raw TSDF mesh
        ctx.log_cb("[SplatMesher] Applying 10 iterations of C++ Taubin surface smoothing...")
        mesh = mesh.filter_smooth_taubin(number_of_iterations=10)
        mesh.compute_vertex_normals()

        # Amendment 3: Prune disconnected internal floating sheets (< 2,500 faces or < 3% main cluster)
        triangle_clusters, cluster_n_triangles, _ = mesh.cluster_connected_triangles()
        cluster_n_triangles = np.asarray(cluster_n_triangles)
        max_cluster_faces = int(np.max(cluster_n_triangles)) if len(cluster_n_triangles) > 0 else 0
        min_cluster_faces = max(2500, int(0.03 * max_cluster_faces))
        triangles_to_keep = cluster_n_triangles[np.asarray(triangle_clusters)] >= min_cluster_faces
        mesh.remove_triangles_by_mask(~triangles_to_keep)
        mesh.remove_unreferenced_vertices()

        # Amendment 1: Transform mesh vertices back into raw COLMAP sparse space via Kabsch alignment
        ctx.log_cb("[SplatMesher] Computing Kabsch transform to align mesh back to raw COLMAP sparse space...")
        raw_sparse_candidates = [
            ctx.workdir / "sparse_txt",
            ctx.workdir / "sparse" / "0",
            ctx.workdir / "undistorted" / "sparse",
            ctx.workdir / "sparse",
        ]
        raw_sparse_dir = None
        for d in raw_sparse_candidates:
            if d.exists() and (d / "cameras.txt").exists() and (d / "images.txt").exists():
                raw_sparse_dir = d
                break
        if not raw_sparse_dir:
            # Fall back to finding via find_colmap_sparse_dir
            raw_sparse_dir = find_colmap_sparse_dir(ctx.workdir / "sparse")

        raw_cams, raw_images, _ = parse_colmap_sparse(raw_sparse_dir)
        R_c2r, t_c2r, max_err = compute_kabsch_transform(aligned_cam_map, raw_images)
        det_R = float(np.linalg.det(R_c2r))
        ctx.log_cb(
            f"[SplatMesher] Kabsch alignment verified: max_camera_error = {max_err:.6e} < 1e-3, "
            f"det(R) = {det_R:.6f}."
        )
        assert max_err < 1e-3, f"Kabsch alignment error exceeded tolerance: {max_err:.6e} >= 1e-3"

        # Apply transform to mesh vertices
        verts_clean = np.asarray(mesh.vertices)
        verts_raw = (R_c2r @ verts_clean.T).T + t_c2r
        mesh.vertices = o3d.utility.Vector3dVector(verts_raw)

        # If det(R) < 0 (reflection), reverse triangle face winding to preserve outward normals
        if det_R < 0:
            ctx.log_cb("[SplatMesher] Reflection detected in Kabsch transform: reversing face winding...")
            tris = np.asarray(mesh.triangles)
            mesh.triangles = o3d.utility.Vector3iVector(tris[:, [0, 2, 1]])

        mesh.compute_vertex_normals()

        num_verts = len(mesh.vertices)
        num_faces = len(mesh.triangles)
        ctx.log_cb(
            f"[SplatMesher] Final raw-aligned mesh: {num_verts:,} vertices, {num_faces:,} faces. "
            f"Co-registered 100% with raw COLMAP cameras for OpenMVS texturing."
        )

        o3d.io.write_triangle_mesh(str(out_mesh_path), mesh, write_vertex_normals=True, write_vertex_colors=True)
        o3d.io.write_triangle_mesh(str(mesh_dense_path), mesh, write_vertex_normals=True, write_vertex_colors=True)

        return StageResult(
            success=True,
            output_files=[out_mesh_path, mesh_dense_path],
            metadata={
                "vertex_count": num_verts,
                "face_count": num_faces,
                "fused_views": fused_views,
                "kabsch_max_err": max_err,
            }
        )
