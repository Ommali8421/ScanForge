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

        # Determine target face count
        options = ctx.params.get("options") or {}
        poly_target: Optional[int] = options.get("poly_target")

        if poly_target is None:
            quality = ctx.params.get("quality", "standard")
            quality_map = {
                "draft": 50_000,
                "standard": 200_000,
                "high": 1_000_000,
                "ultra": None,
            }
            poly_target = quality_map.get(quality, 200_000)

        output_ply = ctx.workdir / "mesh_decimated.ply"

        import open3d as o3d
        o3d_mesh = o3d.io.read_triangle_mesh(str(input_ply))
        initial_faces = len(o3d_mesh.triangles)
        initial_verts = len(o3d_mesh.vertices)
        ctx.log_cb(f"[Decimate] Loaded {initial_verts:,} vertices, {initial_faces:,} faces from {input_ply.name}.")

        if poly_target is None or initial_faces <= poly_target:
            ctx.log_cb(
                f"[Decimate] Mesh faces ({initial_faces:,}) <= target ({poly_target or 'ultra'}); skipping decimation."
            )
            o3d.io.write_triangle_mesh(str(output_ply), o3d_mesh)
            final_faces = initial_faces
            final_verts = initial_verts
        else:
            ctx.log_cb(
                f"[Decimate] Decimating from {initial_faces:,} to {poly_target:,} faces (boundary_weight=1.0)..."
            )
            decimated_mesh = o3d_mesh.simplify_quadric_decimation(
                target_number_of_triangles=poly_target,
                boundary_weight=1.0,
            )
            final_faces = len(decimated_mesh.triangles)
            final_verts = len(decimated_mesh.vertices)
            ctx.log_cb(
                f"[Decimate] Decimation completed: {final_verts:,} vertices, {final_faces:,} faces "
                f"({final_faces / initial_faces * 100:.1f}% of original)."
            )
            o3d.io.write_triangle_mesh(str(output_ply), decimated_mesh)

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
