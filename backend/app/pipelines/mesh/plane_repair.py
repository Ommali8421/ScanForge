"""
Plane Repair Stage (Phase 2)
Performs normal-aware plane snapping, corner regularisation, and spurious surface removal:
- Uses room_analysis.json computed by RoomAnalysisStage in the original SfM frame.
- Only snaps vertices whose normal agrees with the plane normal (|n_v . n_p| > 0.9).
- Correctly projects two-plane corner vertices onto the intersection line (avoiding double projection).
- Leaves furniture and non-planar geometry completely untouched.
- Removes subsurface geometry below the floor and exterior ghost geometry outside the wall envelope.
- Reports percentage of vertices moved and maximum displacement as a fraction of scene diagonal.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
import trimesh

from app.pipelines.base import Stage, StageResult, JobContext


def line_intersection_of_two_planes(n1: np.ndarray, d1: float, n2: np.ndarray, d2: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes the parametric line of intersection between two planes:
    n1 . x + d1 = 0
    n2 . x + d2 = 0
    Returns:
        p_line: a point on the line (closest to origin).
        dir_line: unit direction vector along the line.
    """
    dir_line = np.cross(n1, n2)
    dir_norm = np.linalg.norm(dir_line)
    if dir_norm < 1e-6:
        # Nearly parallel planes
        return -d1 * n1, np.array([0.0, 0.0, 1.0])

    dir_line /= dir_norm

    # Solve least squares for point on line closest to origin:
    # [n1^T; n2^T] * p = [-d1; -d2]
    A = np.vstack([n1, n2])
    b = np.array([-d1, -d2])
    p_line = np.linalg.pinv(A) @ b

    return p_line, dir_line


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Smooth Hermite interpolation between edge0 and edge1, clamping to [0, 1]."""
    if abs(edge1 - edge0) < 1e-9:
        return 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


class PlaneRepairStage(Stage):
    """
    Snaps planar vertices and removes spurious out-of-envelope geometry in SfM frame.
    Outputs: mesh_repaired.ply.
    """
    name: str = "plane_repair"
    weight: float = 1.5
    declared_outputs: List[str] = [
        "mesh_repaired.ply",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[PlaneRepair] Initializing normal-aware plane repair and envelope clipping...")
        t0 = time.time()

        input_ply = ctx.workdir / "mesh_cleaned.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "scene_dense_mesh.ply"
        if not input_ply.exists():
            raise FileNotFoundError(f"[PlaneRepair] Cleaned mesh not found at {input_ply}")

        analysis_json = ctx.workdir / "room_analysis.json"
        if not analysis_json.exists():
            raise FileNotFoundError(
                f"[PlaneRepair] room_analysis.json not found at {analysis_json}. "
                "Ensure RoomAnalysisStage ran before PlaneRepairStage."
            )

        with open(analysis_json, "r") as f:
            analysis = json.load(f)

        scene_diagonal = float(analysis["scene_diagonal"])
        chosen_floor = analysis["chosen_floor_plane"]
        wall_planes = analysis.get("wall_planes", [])

        # Build list of active dominant planes (floor + walls)
        active_planes = []
        # Floor plane
        active_planes.append({
            "name": "floor",
            "normal": np.array(chosen_floor["normal"], dtype=float),
            "d": float(chosen_floor["d"]),
        })
        # Wall planes
        for i, wp in enumerate(wall_planes):
            active_planes.append({
                "name": f"wall_{i}",
                "normal": np.array(wp["normal"], dtype=float),
                "d": float(wp["d"]),
            })

        ctx.log_cb(
            f"[PlaneRepair] Loaded {len(active_planes)} active dominant plane(s) "
            f"(1 floor, {len(wall_planes)} walls). Scene diagonal: {scene_diagonal:.3f}."
        )

        mesh = trimesh.load(str(input_ply), process=False)
        vertices = mesh.vertices.copy()
        normals = mesh.vertex_normals.copy()
        num_vertices = len(vertices)

        # Snap distance threshold: 0.5% of scene diagonal
        snap_thresh = 0.005 * scene_diagonal
        # Normal agreement threshold: |n_v . n_p| > 0.9
        normal_agreement_thresh = 0.90

        vertices_moved = 0
        max_displacement = 0.0
        displacements = []

        ctx.log_cb(
            f"[PlaneRepair] Snapping vertices with |n_v . n_p| > {normal_agreement_thresh} "
            f"within distance {snap_thresh:.4f}..."
        )

        # 1. Normal-aware plane snapping and corner handling
        for i in range(num_vertices):
            v = vertices[i]
            nv = normals[i]
            nv_norm = np.linalg.norm(nv)
            if nv_norm < 1e-6:
                continue
            nv = nv / nv_norm

            matching_planes = []
            for plane in active_planes:
                np_vec = plane["normal"]
                d = plane["d"]
                dot = abs(float(np.dot(nv, np_vec)))

                if dot > normal_agreement_thresh:
                    dist = abs(float(np.dot(np_vec, v) + d))
                    if dist <= snap_thresh:
                        # Soft C1 falloff to prevent sawtooth tearing at boundaries/shelves:
                        # Full weight at dist -> 0 and dot -> 1, smoothly tapering to 0 at cutoff edges
                        w_dist = smoothstep(snap_thresh, 0.0, dist)
                        w_norm = smoothstep(normal_agreement_thresh, 1.0, dot)
                        w = w_dist * w_norm
                        matching_planes.append((plane, dist, w))

            if not matching_planes:
                # Furniture / organic decoration: leave untouched
                continue

            if len(matching_planes) == 1:
                # Soft projection onto single dominant plane
                plane, dist, w = matching_planes[0]
                np_vec = plane["normal"]
                d = plane["d"]
                displacement_vector = -w * (np.dot(np_vec, v) + d) * np_vec
                disp = float(np.linalg.norm(displacement_vector))
                if disp > 1e-6:
                    vertices[i] = v + displacement_vector
                    vertices_moved += 1
                    displacements.append(disp)
                    if disp > max_displacement:
                        max_displacement = disp

            elif len(matching_planes) >= 2:
                # Corner regularisation: project onto intersection line with blended soft weight
                p1, dist1, w1 = matching_planes[0]
                p2, dist2, w2 = matching_planes[1]
                n1, d1 = p1["normal"], p1["d"]
                n2, d2 = p2["normal"], p2["d"]
                w_corner = min(w1, w2)

                p_line, dir_line = line_intersection_of_two_planes(n1, d1, n2, d2)
                v_target = p_line + np.dot(v - p_line, dir_line) * dir_line
                displacement_vector = w_corner * (v_target - v)
                disp = float(np.linalg.norm(displacement_vector))
                if disp > 1e-6 and disp <= snap_thresh * 1.5:
                    vertices[i] = v + displacement_vector
                    vertices_moved += 1
                    displacements.append(disp)
                    if disp > max_displacement:
                        max_displacement = disp

        pct_moved = (vertices_moved / num_vertices * 100) if num_vertices > 0 else 0.0
        max_disp_fraction = (max_displacement / scene_diagonal) if scene_diagonal > 0 else 0.0

        ctx.log_cb(
            f"[PlaneRepair] Regularized {vertices_moved:,}/{num_vertices:,} vertices ({pct_moved:.1f}%). "
            f"Max displacement: {max_displacement:.4f} ({max_disp_fraction*100:.2f}% of scene diagonal)."
        )

        mesh.vertices = vertices

        # 2. Geometry Removal: Below Floor & Outside Wall Envelope (Conservative Enveloping)
        # Geometry inside the expanded camera-trajectory bounding box is strictly protected.
        face_centers = mesh.triangles_center
        if "cam_bbox_min" in analysis and "cam_bbox_max" in analysis:
            cam_min = np.array(analysis["cam_bbox_min"], dtype=float)
            cam_max = np.array(analysis["cam_bbox_max"], dtype=float)
            cam_margin = 0.15 * scene_diagonal
            cam_envelope_min = cam_min - cam_margin
            cam_envelope_max = cam_max + cam_margin
            inside_cam_envelope = np.all((face_centers >= cam_envelope_min) & (face_centers <= cam_envelope_max), axis=1)
        else:
            inside_cam_envelope = np.zeros(len(mesh.faces), dtype=bool)

        # Floor pruning: strictly outside camera envelope AND beyond floor plane with margin
        floor_n = np.array(chosen_floor["normal"], dtype=float)
        floor_d = float(chosen_floor["d"])
        below_floor_margin = 0.01 * scene_diagonal
        face_signed_floor = np.dot(face_centers, floor_n) + floor_d
        below_floor_faces = (face_signed_floor < -below_floor_margin) & (~inside_cam_envelope)

        # Wall envelope pruning: require at least 2 strong wall planes (>= 1000 inliers)
        # Never prune on a single weak or single active wall plane to avoid half-space slicing.
        strong_walls = [wp for wp in wall_planes if wp.get("inliers", 0) >= 1000]
        outside_wall_faces = np.zeros(len(mesh.faces), dtype=bool)
        wall_margin = 0.02 * scene_diagonal

        if len(strong_walls) >= 2:
            for wp in strong_walls:
                wn = np.array(wp["normal"], dtype=float)
                wd = float(wp["d"])
                face_signed_wall = np.dot(face_centers, wn) + wd
                outside_wall_faces |= (face_signed_wall < -wall_margin) & (~inside_cam_envelope)
        else:
            ctx.log_cb(
                f"[PlaneRepair] Wall envelope pruning disabled: found {len(strong_walls)} strong wall(s) (minimum 2 required)."
            )

        drop_mask = below_floor_faces | outside_wall_faces
        dropped_floor_count = int(np.sum(below_floor_faces))
        dropped_wall_count = int(np.sum(outside_wall_faces & ~below_floor_faces))
        total_dropped = int(np.sum(drop_mask))

        ctx.log_cb(
            f"[PlaneRepair] Pruning spurious out-of-envelope geometry: "
            f"{dropped_floor_count:,} faces below floor, {dropped_wall_count:,} faces outside wall envelope "
            f"({total_dropped:,} total faces pruned)."
        )

        if total_dropped > 0:
            mesh.update_faces(~drop_mask)
            mesh.remove_unreferenced_vertices()

        output_ply = ctx.workdir / "mesh_repaired.ply"
        mesh.export(str(output_ply))
        ctx.log_cb(
            f"[PlaneRepair] Plane repair completed in {time.time() - t0:.2f}s: "
            f"{len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces saved to {output_ply.name}."
        )

        return StageResult(
            success=True,
            output_files=[output_ply],
            metadata={
                "vertices_snapped": vertices_moved,
                "percentage_vertices_snapped": round(pct_moved, 2),
                "max_displacement": round(max_displacement, 5),
                "max_displacement_diagonal_fraction": round(max_disp_fraction, 5),
                "dropped_below_floor_faces": dropped_floor_count,
                "dropped_outside_wall_faces": dropped_wall_count,
                "repaired_vertices": len(mesh.vertices),
                "repaired_faces": len(mesh.faces),
            },
        )

