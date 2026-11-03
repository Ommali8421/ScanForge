"""
Poisson Surface Reconstruction A/B Stage (Phase 2 Requirement C.5)
Executes Open3D Screened Poisson Surface Reconstruction on the dense point cloud:
- Camera-oriented normals towards calibrated camera optical centers.
- Density-trimmed to remove low-confidence exterior surfaces.
- Emits mesh_poisson.ply and mesh_poisson.glb for A/B comparison against Delaunay mesh.
"""

import time
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import trimesh

from app.pipelines.base import Stage, StageResult, JobContext
from app.pipelines.mesh.room_analysis import parse_camera_poses_from_workdir


class PoissonABStage(Stage):
    """
    Open3D Poisson surface reconstruction on the dense point cloud.
    Allows side-by-side A/B comparison against OpenMVS Delaunay ReconstructMesh.
    Outputs: mesh_poisson.ply, mesh_poisson.glb.
    """
    name: str = "poisson_ab"
    weight: float = 2.0
    declared_outputs: List[str] = [
        "mesh_poisson.ply",
        "mesh_poisson.glb",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[PoissonAB] Initializing Open3D Poisson surface reconstruction A/B test...")
        t0 = time.time()

        dense_ply = ctx.workdir / "scene_dense.ply"
        if not dense_ply.exists():
            dense_ply = ctx.workdir / "dense_cloud.ply"
        if not dense_ply.exists():
            ctx.log_cb("[PoissonAB] No dense point cloud found for Poisson A/B test. Skipping.")
            return StageResult(success=True, skipped_cache=True)

        output_ply = ctx.workdir / "mesh_poisson.ply"
        output_glb = ctx.workdir / "mesh_poisson.glb"

        import open3d as o3d
        ctx.log_cb(f"[PoissonAB] Loading dense cloud from {dense_ply.name}...")
        pcd = o3d.io.read_point_cloud(str(dense_ply))
        num_points = len(pcd.points)
        ctx.log_cb(f"[PoissonAB] Loaded {num_points:,} dense points.")

        # 1. Camera-oriented normals
        centers, _, _ = parse_camera_poses_from_workdir(ctx.workdir)
        if len(centers) > 0:
            if not pcd.has_normals():
                ctx.log_cb("[PoissonAB] Estimating point cloud normals (hybrid radius=0.1, max_nn=30)...")
                pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))

            ctx.log_cb("[PoissonAB] Orienting point normals towards nearest camera centers (vectorized cKDTree)...")
            from scipy.spatial import cKDTree
            pts = np.asarray(pcd.points)
            normals = np.asarray(pcd.normals)
            cam_tree = cKDTree(centers)
            _, nearest_cam_indices = cam_tree.query(pts)
            nearest_centers = centers[nearest_cam_indices]
            view_dirs = nearest_centers - pts
            dots = np.einsum("ij,ij->i", normals, view_dirs)
            flip_mask = dots < 0
            oriented_normals = normals.copy()
            oriented_normals[flip_mask] = -normals[flip_mask]
            pcd.normals = o3d.utility.Vector3dVector(oriented_normals)
        else:
            if not pcd.has_normals():
                pcd.estimate_normals()
                pcd.orient_normals_consistent_tangent_plane(15)

        # 2. Run Screened Poisson Surface Reconstruction (depth=9)
        ctx.log_cb("[PoissonAB] Running Screened Poisson Surface Reconstruction (octree depth=9)...")
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd,
            depth=9,
            width=0,
            scale=1.1,
            linear_fit=False,
        )

        initial_poisson_faces = len(mesh.triangles)
        ctx.log_cb(f"[PoissonAB] Raw Poisson mesh has {initial_poisson_faces:,} triangles.")

        # 3. Density trimming (prune lowest 5% quantile of vertices)
        densities_arr = np.asarray(densities)
        if len(densities_arr) > 0:
            density_threshold = np.percentile(densities_arr, 5)
            ctx.log_cb(f"[PoissonAB] Trimming low-density vertices (threshold < {density_threshold:.3f})...")
            vertices_to_remove = densities_arr < density_threshold
            mesh.remove_vertices_by_mask(vertices_to_remove)
            mesh.remove_unreferenced_vertices()

        final_verts = len(mesh.vertices)
        final_faces = len(mesh.triangles)
        ctx.log_cb(
            f"[PoissonAB] Trimmed Poisson mesh: {final_verts:,} vertices, {final_faces:,} faces."
        )

        # Save PLY and GLB
        o3d.io.write_triangle_mesh(str(output_ply), mesh)

        # Convert to GLB with neutral material
        tri_mesh = trimesh.load(str(output_ply), process=False)
        tri_mesh.export(str(output_glb))

        ctx.log_cb(f"[PoissonAB] Exported Poisson A/B mesh to {output_ply.name} and {output_glb.name} in {time.time() - t0:.2f}s.")

        return StageResult(
            success=True,
            output_files=[output_ply, output_glb],
            metadata={
                "poisson_vertices": final_verts,
                "poisson_faces": final_faces,
                "dense_points_input": num_points,
            },
        )
