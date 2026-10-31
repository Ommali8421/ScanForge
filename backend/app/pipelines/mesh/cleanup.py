"""
Mesh Cleanup Stage (Phase 2)
Removes small disconnected floaters (<1% face count of largest component)
and repairs non-manifold / degenerate mesh geometry in the original SfM frame.
"""

import time
from pathlib import Path
from typing import List
import numpy as np
import trimesh

from app.pipelines.base import Stage, StageResult, JobContext


class MeshCleanupStage(Stage):
    """
    Cleans raw Delaunay mesh in original SfM camera coordinate system:
    1. Removes isolated floating mesh components with <1% face count of primary room.
    2. Resolves degenerate triangles, duplicate faces, and unreferenced vertices.
    3. Exports mesh_cleaned.ply.
    """
    name: str = "mesh_cleanup"
    weight: float = 1.0
    declared_outputs: List[str] = [
        "mesh_cleaned.ply",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[MeshCleanup] Initializing mesh floater removal and topological cleanup...")
        t0 = time.time()

        input_ply = ctx.workdir / "scene_dense_mesh.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "raw_mesh.ply"
        if not input_ply.exists():
            raise FileNotFoundError(
                f"[MeshCleanup] Input mesh not found at {input_ply}. "
                "Ensure OpenMVSRMeshStage ran successfully."
            )

        output_ply = ctx.workdir / "mesh_cleaned.ply"

        ctx.log_cb(f"[MeshCleanup] Loading geometry from {input_ply.name}...")
        mesh = trimesh.load(str(input_ply), process=False)
        if not isinstance(mesh, trimesh.Trimesh):
            if hasattr(mesh, "geometry") and mesh.geometry:
                mesh = trimesh.util.concatenate([g for g in mesh.geometry.values() if isinstance(g, trimesh.Trimesh)])
            else:
                raise ValueError(f"[MeshCleanup] Unexpected geometry format in {input_ply}")

        initial_verts = len(mesh.vertices)
        initial_faces = len(mesh.faces)
        ctx.log_cb(f"[MeshCleanup] Initial mesh has {initial_verts:,} vertices and {initial_faces:,} faces.")

        # 1. Connected components analysis for floater removal
        face_components = trimesh.graph.connected_components(mesh.face_adjacency)
        num_components = len(face_components)
        ctx.log_cb(f"[MeshCleanup] Identified {num_components:,} connected component(s).")

        if num_components > 1:
            component_sizes = [len(c) for c in face_components]
            max_size = max(component_sizes)
            min_face_threshold = max(20, int(0.01 * max_size))  # < 1% of primary component

            kept_face_indices = []
            floater_components = 0
            dropped_floater_faces = 0

            for comp in face_components:
                if len(comp) >= min_face_threshold:
                    kept_face_indices.extend(comp)
                else:
                    floater_components += 1
                    dropped_floater_faces += len(comp)

            ctx.log_cb(
                f"[MeshCleanup] Pruned {floater_components:,} small floater component(s) "
                f"({dropped_floater_faces:,} faces dropped, threshold: <{min_face_threshold:,} faces)."
            )

            if kept_face_indices:
                kept_face_mask = np.zeros(len(mesh.faces), dtype=bool)
                kept_face_mask[kept_face_indices] = True
                mesh.update_faces(kept_face_mask)
                mesh.remove_unreferenced_vertices()

        # 2. Topological repair
        mesh.update_faces(mesh.unique_faces())
        mesh.update_faces(mesh.nondegenerate_faces())
        mesh.remove_unreferenced_vertices()

        final_verts = len(mesh.vertices)
        final_faces = len(mesh.faces)
        pct_kept = (final_faces / initial_faces * 100) if initial_faces > 0 else 100.0

        ctx.log_cb(
            f"[MeshCleanup] Cleanup complete in {time.time() - t0:.2f}s: "
            f"{final_verts:,} vertices, {final_faces:,} faces remaining ({pct_kept:.1f}% kept)."
        )

        mesh.export(str(output_ply))
        ctx.log_cb(f"[MeshCleanup] Exported cleaned mesh to {output_ply.name}.")

        return StageResult(
            success=True,
            output_files=[output_ply],
            metadata={
                "initial_vertices": initial_verts,
                "initial_faces": initial_faces,
                "cleaned_vertices": final_verts,
                "cleaned_faces": final_faces,
                "components_found": num_components,
            },
        )
