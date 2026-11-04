"""
Decimate Stage (Phase 2)
Performs planarity-preserving quadric decimation with boundary weight 1.0
to reach target polygon counts in the original SfM frame.
"""

import time
from pathlib import Path
from typing import List, Optional

from app.pipelines.base import Stage, StageResult, JobContext


class DecimateStage(Stage):
    """
    Simplifies interior surface mesh using Open3D quadric decimation:
    simplify_quadric_decimation(target_number_of_triangles, boundary_weight=1.0).
    Boundary weight 1.0 strictly preserves corner junctions, doorways, and wall-floor boundaries.
    Outputs: mesh_decimated.ply.
    """
    name: str = "decimate"
    weight: float = 1.0
    declared_outputs: List[str] = [
        "mesh_decimated.ply",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Decimate] Initializing planarity-preserving quadric decimation...")
        t0 = time.time()

        input_ply = ctx.workdir / "mesh_repaired.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "mesh_cleaned.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "scene_dense_mesh.ply"
        if not input_ply.exists():
            raise FileNotFoundError(f"[Decimate] Input mesh not found at {input_ply}")

        output_ply = ctx.workdir / "mesh_decimated.ply"

        import open3d as o3d
        o3d_mesh = o3d.io.read_triangle_mesh(str(input_ply))
        initial_faces = len(o3d_mesh.triangles)
        initial_verts = len(o3d_mesh.vertices)
        ctx.log_cb(f"[Decimate] Loaded {initial_verts:,} vertices, {initial_faces:,} faces from {input_ply.name}.")

        # Determine target face count with architectural/large scene adaptation
        options = ctx.params.get("options") or {}
        poly_target: Optional[int] = options.get("poly_target")
        quality = str(ctx.params.get("quality", "standard")).lower()

        # Check dense points from scene_dense.ply if available
        dense_points_count = 0
        dense_ply = ctx.workdir / "scene_dense.ply"
        if dense_ply.exists():
            try:
                with open(dense_ply, "r", encoding="latin1") as f:
                    for _ in range(30):
                        line = f.readline()
                        if line.startswith("element vertex"):
                            dense_points_count = int(line.strip().split()[-1])
                            break
            except Exception:
                pass

        is_large_scene = (
            (initial_faces > 600_000) or
            (initial_verts > 1_500_000) or
            (dense_points_count > 1_500_000)
        )

        if poly_target is None or poly_target in (200_000, 250_000):
            if is_large_scene:
                if quality == "high":
                    poly_target = 500_000
                elif quality in ("standard", "auto"):
                    poly_target = 350_000  # 300k-400k target for complex halls
                elif quality == "draft":
                    poly_target = 100_000
                else:
                    poly_target = 350_000
                ctx.log_cb(
                    f"[Decimate] Large architectural scene detected ({initial_verts:,} verts, {initial_faces:,} faces, {dense_points_count:,} dense pts). "
                    f"Elevating decimation ceiling to {poly_target:,} faces for {quality} quality."
                )
            elif poly_target is None:
                quality_map = {
                    "draft": 50_000,
                    "standard": 250_000,
                    "high": 400_000,
                    "ultra": None,
                }
                poly_target = quality_map.get(quality, 250_000)

        if poly_target is None or initial_faces <= poly_target:
            ctx.log_cb(
                f"[Decimate] Mesh faces ({initial_faces:,}) <= target ({poly_target or 'ultra'}); skipping quadric decimation."
            )
            target_mesh = o3d_mesh
        else:
            ctx.log_cb(
                f"[Decimate] Decimating from {initial_faces:,} to {poly_target:,} faces with border locking (boundary_weight=10.0)..."
            )
            target_mesh = o3d_mesh.simplify_quadric_decimation(
                target_number_of_triangles=poly_target,
                boundary_weight=10.0,
            )

        # Post-decimation plane-safe spike filter:
        # Exempts triangles lying on confirmed RANSAC planes (walls/floors/ceilings)
        # to prevent cutting Swiss-cheese holes into flat surfaces where quadric decimation intentionally created large faces.
        import numpy as np
        import json
        verts_np = np.asarray(target_mesh.vertices)
        tris_np = np.asarray(target_mesh.triangles)

        if len(tris_np) > 0 and len(verts_np) > 0:
            v0 = verts_np[tris_np[:, 0]]
            v1 = verts_np[tris_np[:, 1]]
            v2 = verts_np[tris_np[:, 2]]

            e0 = np.linalg.norm(v0 - v1, axis=1)
            e1 = np.linalg.norm(v1 - v2, axis=1)
            e2 = np.linalg.norm(v2 - v0, axis=1)

            all_e = np.concatenate([e0, e1, e2])
            med_edge = float(np.median(all_e))
            max_e = np.maximum(e0, np.maximum(e1, e2))

            # Heron's area to detect extreme needle slivers
            perim = e0 + e1 + e2
            s = perim / 2.0
            area_sq = np.maximum(0.0, s * (s - e0) * (s - e1) * (s - e2))
            area = np.sqrt(area_sq)
            aspect_ratio_sq = (perim ** 2) / (area + 1e-12)

            # Load active RANSAC planes to protect flat walls/floors
            active_planes = []
            scene_diag = 20.0
            analysis_json = ctx.workdir / "room_analysis.json"
            if analysis_json.exists():
                try:
                    with open(analysis_json, "r") as f:
                        ra = json.load(f)
                    scene_diag = float(ra.get("scene_diagonal", 20.0))
                    if ra.get("chosen_floor_plane"):
                        active_planes.append(ra["chosen_floor_plane"])
                    for wp in ra.get("wall_planes", []):
                        active_planes.append(wp)
                except Exception:
                    pass

            is_on_plane = np.zeros(len(tris_np), dtype=bool)
            plane_dist_thresh = max(0.02 * scene_diag, 0.08)
            for p in active_planes:
                pn = np.array(p["normal"], dtype=float)
                pd = float(p["d"])
                d0 = np.abs(np.dot(v0, pn) + pd)
                d1 = np.abs(np.dot(v1, pn) + pd)
                d2 = np.abs(np.dot(v2, pn) + pd)
                is_on_plane |= (d0 < plane_dist_thresh) & (d1 < plane_dist_thresh) & (d2 < plane_dist_thresh)

            # Planar triangles: only prune extreme cross-space spikes (> 8.0x median)
            # Non-planar triangles: prune spikes > 4.5x median or extreme slivers
            is_spike = np.where(
                is_on_plane,
                max_e > 8.0 * med_edge,
                (max_e > 4.5 * med_edge) | ((max_e > 2.0 * med_edge) & (aspect_ratio_sq > 80.0))
            )
            num_spikes = int(np.sum(is_spike))

            if num_spikes > 0:
                ctx.log_cb(
                    f"[Decimate] Plane-safe spike filter dropped {num_spikes:,} spurious long-edge/sliver faces "
                    f"(median edge length {med_edge:.4f}m; {int(np.sum(is_on_plane)):,} planar faces protected). "
                    f"Max edge reduced from {np.max(max_e):.3f}m to {np.max(max_e[~is_spike]):.3f}m."
                )
                target_mesh.remove_triangles_by_mask(is_spike)
                target_mesh.remove_unreferenced_vertices()

        final_faces = len(target_mesh.triangles)
        final_verts = len(target_mesh.vertices)
        ctx.log_cb(
            f"[Decimate] Decimation & spike filtering completed: {final_verts:,} vertices, {final_faces:,} faces "
            f"({final_faces / initial_faces * 100:.1f}% of original)."
        )
        o3d.io.write_triangle_mesh(str(output_ply), target_mesh)

        ctx.log_cb(f"[Decimate] Exported decimated mesh to {output_ply.name} in {time.time() - t0:.2f}s.")

        return StageResult(
            success=True,
            output_files=[output_ply],
            metadata={
                "initial_faces": initial_faces,
                "final_faces": final_faces,
                "target_faces": poly_target,
                "reduction_ratio": round(final_faces / initial_faces, 3) if initial_faces > 0 else 1.0,
            },
        )
