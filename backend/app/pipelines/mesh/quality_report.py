"""
Quality Report Stage
Analyzes the final aligned, physically-scaled interior reconstruction and produces
a comprehensive geometric quality and architectural dimension report.
Outputs:
- quality_report.json (consumed by GET /api/jobs/{id}/report and frontend QualityReport.tsx)
"""

import json
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import trimesh

from app.pipelines.base import Stage, JobContext, StageResult
from app.utils.logging import logger


def generate_quality_report_dict(
    mesh: trimesh.Trimesh,
    cumulative_scale: float = 1.0,
    up_axis: str = "y",
    is_calibrated: bool = False
) -> Dict[str, Any]:
    """Computes geometric metrics, room dimensions, and quality assessment."""
    verts = mesh.vertices
    faces = mesh.faces

    vertex_count = int(len(verts))
    face_count = int(len(faces))

    # Topology and watertightness
    is_watertight = bool(mesh.is_watertight)

    # Edge analysis
    edges_sorted = np.sort(mesh.edges, axis=1)
    _, counts = np.unique(edges_sorted, axis=0, return_counts=True)
    open_edges = int(np.sum(counts == 1))
    non_manifold_edges = int(np.sum(counts > 2))

    # Rough boundary hole loop estimate
    hole_count = max(0, int(open_edges // 30)) if not is_watertight else 0

    # Dimensions
    bounds_min = verts.min(axis=0)
    bounds_max = verts.max(axis=0)
    extents = bounds_max - bounds_min

    if up_axis.lower() == "z":
        length = float(round(extents[0], 2))
        width = float(round(extents[1], 2))
        height = float(round(extents[2], 2))
    else:  # Y up
        length = float(round(extents[0], 2))
        height = float(round(extents[1], 2))
        width = float(round(extents[2], 2))

    # Floor Area: Sum of horizontal face areas near floor level (Y ≈ 0)
    up_idx = 2 if up_axis.lower() == "z" else 1
    floor_threshold = 0.15 * max(height, 0.5)
    face_centers = mesh.triangles_center
    face_normals = mesh.face_normals

    near_floor = face_centers[:, up_idx] < floor_threshold
    horizontal_faces = np.abs(face_normals[:, up_idx]) > 0.8
    floor_face_mask = near_floor & horizontal_faces

    sum_face_area = float(np.sum(mesh.area_faces[floor_face_mask])) if np.sum(floor_face_mask) > 10 else 0.0

    # Compute 2D robust hull of floor/interior vertices to guard against missing floor faces
    try:
        from scipy.spatial import ConvexHull
        horiz_indices = [0, 2] if up_idx == 1 else [0, 1]
        v_2d = mesh.vertices[:, horiz_indices]
        p2 = np.percentile(v_2d, 2, axis=0)
        p98 = np.percentile(v_2d, 98, axis=0)
        inlier_mask = (v_2d[:, 0] >= p2[0]) & (v_2d[:, 0] <= p98[0]) & (v_2d[:, 1] >= p2[1]) & (v_2d[:, 1] <= p98[1])
        hull = ConvexHull(v_2d[inlier_mask])
        hull_area = float(hull.volume)
    except Exception:
        hull_area = length * width * 0.70

    if sum_face_area >= 0.40 * hull_area:
        floor_area_sqm = float(round(sum_face_area, 2))
    else:
        floor_area_sqm = float(round(max(sum_face_area, 0.75 * hull_area), 2))

    # Quality Grade heuristic
    if is_watertight and non_manifold_edges == 0:
        quality_grade = "A"
    elif non_manifold_edges < 100:
        quality_grade = "B"
    else:
        quality_grade = "C"

    report = {
        "vertex_count": vertex_count,
        "face_count": face_count,
        "hole_count": hole_count,
        "is_watertight": is_watertight,
        "non_manifold_edges": non_manifold_edges,
        "dimensions_meters": {
            "length": length,
            "width": width,
            "height": height
        },
        "floor_area_sqm": floor_area_sqm,
        "cumulative_scale": round(float(cumulative_scale), 4),
        "up_axis": up_axis.lower(),
        "is_calibrated": is_calibrated,
        "quality_grade": quality_grade
    }
    return report


class QualityReportStage(Stage):
    """
    Computes topology metrics, room dimensions, and quality grade.
    Emits quality_report.json.
    """
    name = "quality_report"
    weight = 0.5
    declared_inputs = ["aligned_textured.glb"]
    declared_outputs = ["quality_report.json"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb(f"[{self.name}] (0%) Analyzing interior geometry and room dimensions...")

        in_glb = ctx.workdir / "aligned_textured.glb"
        if not in_glb.exists():
            in_glb = ctx.workdir / "mesh.glb"
        if not in_glb.exists():
            in_glb = ctx.workdir / "scene_textured.glb"
        if not in_glb.exists():
            in_glb = ctx.workdir / "aligned_mesh.ply"

        if not in_glb.exists():
            if ctx.params.get("scan_type") in ("gaussian_splat", "3dgs") and not ctx.params.get("options", {}).get("include_mesh"):
                ctx.log_cb(f"[{self.name}] 3DGS quality report already emitted by SplatCleanup. Skipping mesh quality reporting.")
                return StageResult(success=True, skipped_cache=True)
            return StageResult(success=False, metadata={"error": "No mesh available for quality reporting."})

        loaded = trimesh.load(str(in_glb), process=False)
        if isinstance(loaded, trimesh.Scene):
            geoms = list(loaded.geometry.values())
            mesh = geoms[0] if geoms else trimesh.Trimesh()
        else:
            mesh = loaded

        opts = ctx.params.get("options", {})
        up_axis = str(opts.get("up_axis", "y"))
        scale = float(ctx.cumulative_scale or 1.0)
        is_calibrated = bool(opts.get("is_calibrated", False) or scale != 1.0)

        report_data = generate_quality_report_dict(
            mesh=mesh,
            cumulative_scale=scale,
            up_axis=up_axis,
            is_calibrated=is_calibrated
        )

        out_json = ctx.workdir / "quality_report.json"
        out_json.write_text(json.dumps(report_data, indent=2))

        ctx.log_cb(
            f"[{self.name}] (100%) Quality Report complete: "
            f"{report_data['dimensions_meters']['length']}m x {report_data['dimensions_meters']['width']}m x {report_data['dimensions_meters']['height']}m, "
            f"Floor Area: {report_data['floor_area_sqm']} m², Grade: {report_data['quality_grade']}."
        )

        return StageResult(
            success=True,
            output_files=[out_json],
            metadata=report_data
        )

