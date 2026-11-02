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

        # 2. Camera-trajectory safe bounding box pruning
        # Prevents wild Delaunay artifacts outside windows while strictly protecting ceilings and floors
        try:
            from app.pipelines.mesh.room_analysis import parse_camera_poses_from_workdir
            cams, _, u_grav = parse_camera_poses_from_workdir(ctx.workdir)
            if len(cams) >= 4 and len(mesh.faces) > 0:
                u_grav = np.array(u_grav, dtype=float)
                if np.linalg.norm(u_grav) > 1e-6:
                    u_grav = u_grav / np.linalg.norm(u_grav)
                else:
                    u_grav = np.array([0.0, 1.0, 0.0])

                cam_min = np.min(cams, axis=0)
                cam_max = np.max(cams, axis=0)
                cam_span = cam_max - cam_min

                vert_axis = int(np.argmax(np.abs(u_grav)))
                horiz_axes = [i for i in range(3) if i != vert_axis]
                horiz_cam_span = float(max(cam_span[horiz_axes[0]], cam_span[horiz_axes[1]]))

                # Project camera centers onto u_grav for true vertical span
                cam_dots = np.dot(cams, u_grav)
                cam_span_vert = float(np.max(cam_dots) - np.min(cam_dots))

                vert_margin = float(max(1.4 * cam_span_vert, 0.65 * horiz_cam_span, 2.5))
                horiz_margin = float(max(1.8 * horiz_cam_span, 3.5))

                margins = np.full(3, horiz_margin)
                margins[vert_axis] = vert_margin

                env_min = cam_min - margins
                env_max = cam_max + margins

                face_centers = mesh.triangles_center
                inside_box = np.all((face_centers >= env_min) & (face_centers <= env_max), axis=1)
                face_dots = np.dot(face_centers, u_grav)
                inside_vert = (face_dots >= (np.min(cam_dots) - vert_margin)) & (face_dots <= (np.max(cam_dots) + vert_margin))
                inside_env = inside_box & inside_vert

                dropped_env = int(np.sum(~inside_env))
                if dropped_env > 0:
                    mesh.update_faces(inside_env)
                    mesh.remove_unreferenced_vertices()
                    ctx.log_cb(
                        f"[MeshCleanup] Pruned {dropped_env:,} exterior faces outside camera-trajectory envelope "
                        f"(cam_span_vert={cam_span_vert:.2f}m, horiz_cam_span={horiz_cam_span:.2f}m, "
                        f"horiz_margin={horiz_margin:.2f}m, vert_margin={vert_margin:.2f}m)."
                    )
        except Exception as e:
            ctx.log_cb(f"[MeshCleanup] Note: Bounding envelope check skipped ({e}).")

        # 3. Pre-repair spike and extreme needle-sliver filtering
        if len(mesh.faces) > 0:
            edges = mesh.edges_unique_length
            if len(edges) > 0:
                med_edge = float(np.median(edges))
                tri_edges = mesh.edges_unique[mesh.faces_unique_edges]
                # Length of 3 edges per face
                v = mesh.vertices
                f = mesh.faces
                e0 = np.linalg.norm(v[f[:, 0]] - v[f[:, 1]], axis=1)
                e1 = np.linalg.norm(v[f[:, 1]] - v[f[:, 2]], axis=1)
                e2 = np.linalg.norm(v[f[:, 2]] - v[f[:, 0]], axis=1)
                max_edge = np.maximum(e0, np.maximum(e1, e2))
                perim = e0 + e1 + e2
                areas = mesh.area_faces
                aspect_ratio = (perim ** 2) / (4.0 * np.sqrt(3.0) * (areas + 1e-12))

                is_spike = (max_edge > 4.5 * med_edge) | ((max_edge > 2.0 * med_edge) & (aspect_ratio > 40.0))
                dropped_spikes = int(np.sum(is_spike))
                if dropped_spikes > 0:
                    mesh.update_faces(~is_spike)
                    mesh.remove_unreferenced_vertices()
                    ctx.log_cb(
                        f"[MeshCleanup] Pruned {dropped_spikes:,} pre-repair needle spikes/slivers "
                        f"(edge > 4.5x median {med_edge:.4f}m or aspect > 40.0)."
                    )

        # 4. Topological repair
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
