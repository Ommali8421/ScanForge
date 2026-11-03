"""
2D Floor Plan Generator (Milestone P4)
Extracts horizontal cross-sections of interior meshes at eye/waist level:
  - If calibrated: Y_slice = 1.10 * cumulative_scale
  - If uncalibrated: Y_slice = clamp(0.65 * median_cam_y, 0.25 * H_room, 0.55 * H_room)
Outputs architectural 2D floor plans:
  - floor_plan.svg (scalable blueprint vector)
  - floor_plan.png (rasterized high-resolution preview)
Includes update_floor_plan_scale() hook for /api/jobs/{id}/calibrate synchronization.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.pipelines.base import Stage, JobContext, StageResult
from app.utils.logging import logger


def compute_slice_height(
    y_floor: float,
    y_ceiling: float,
    median_cam_y: float,
    cumulative_scale: float,
    is_calibrated: bool,
) -> float:
    """
    Computes dynamic slice height per Mandatory Amendment 2:
    - Calibrated: 1.10 * cumulative_scale
    - Uncalibrated: clamp(0.65 * median_cam_y, 0.25 * H_room, 0.55 * H_room)
    """
    h_room = max(y_ceiling - y_floor, 0.5)
    if is_calibrated:
        y_slice = 1.10 * cumulative_scale
        # Guard against slicing above ceiling
        if y_slice >= (y_ceiling - 0.2):
            y_slice = y_floor + 0.45 * h_room
        return float(y_slice)
    else:
        # Dynamic uncalibrated slice
        target_cam_h = 0.65 * median_cam_y
        min_h = 0.25 * h_room
        max_h = 0.55 * h_room
        y_slice_rel = np.clip(target_cam_h, min_h, max_h)
        return float(y_floor + y_slice_rel)


def slice_mesh_xz(mesh_path: Path, y_slice: float) -> Tuple[np.ndarray, Tuple[float, float, float, float]]:
    """
    Computes intersection segments between mesh and horizontal plane Y = Y_slice.
    Returns:
      segments_2d: (N, 2, 2) array of (x, z) coordinates
      bounds: (min_x, max_x, min_z, max_z)
    """
    import trimesh

    loaded = trimesh.load(str(mesh_path))
    if hasattr(loaded, "geometry") and loaded.geometry:
        mesh = list(loaded.geometry.values())[0]
    else:
        mesh = loaded

    # Find triangles intersecting the horizontal plane Y = y_slice
    lines_3d = trimesh.intersections.mesh_plane(
        mesh,
        plane_normal=[0.0, 1.0, 0.0],
        plane_origin=[0.0, y_slice, 0.0]
    )

    if lines_3d is None or len(lines_3d) == 0:
        # Fallback: slice slightly lower or higher if empty
        for offset in [-0.2, 0.2, -0.4, 0.4]:
            lines_3d = trimesh.intersections.mesh_plane(
                mesh,
                plane_normal=[0.0, 1.0, 0.0],
                plane_origin=[0.0, y_slice + offset, 0.0]
            )
            if lines_3d is not None and len(lines_3d) > 0:
                break

    if lines_3d is None or len(lines_3d) == 0:
        # Generate bounding box contour fallback
        bbox = mesh.bounds
        p0, p1 = bbox[0], bbox[1]
        lines_3d = np.array([
            [[p0[0], y_slice, p0[2]], [p1[0], y_slice, p0[2]]],
            [[p1[0], y_slice, p0[2]], [p1[0], y_slice, p1[2]]],
            [[p1[0], y_slice, p1[2]], [p0[0], y_slice, p1[2]]],
            [[p0[0], y_slice, p1[2]], [p0[0], y_slice, p0[2]]],
        ])

    # Extract 2D (x, z) coordinates
    segments_2d = lines_3d[:, :, [0, 2]]  # (N, 2, 2)

    # Filter out near-zero length segments
    diffs = segments_2d[:, 1, :] - segments_2d[:, 0, :]
    lens = np.linalg.norm(diffs, axis=1)
    valid = lens > 1e-3
    segments_2d = segments_2d[valid]

    all_pts = segments_2d.reshape(-1, 2)
    min_x = float(np.min(all_pts[:, 0]))
    max_x = float(np.max(all_pts[:, 0]))
    min_z = float(np.min(all_pts[:, 1]))
    max_z = float(np.max(all_pts[:, 1]))

    return segments_2d, (min_x, max_x, min_z, max_z)


def render_floor_plan_svg(
    segments_2d: np.ndarray,
    bounds: Tuple[float, float, float, float],
    output_path: Path,
    dimensions: Dict[str, float],
    is_calibrated: bool,
    y_slice: float,
):
    """
    Renders vector architectural blueprint SVG.
    """
    min_x, max_x, min_z, max_z = bounds
    width_units = max(max_x - min_x, 0.1)
    depth_units = max(max_z - min_z, 0.1)

    svg_w, svg_h = 1600, 1200
    margin = 120
    draw_w = svg_w - 2 * margin
    draw_h = svg_h - 2 * margin

    scale = min(draw_w / width_units, draw_h / depth_units)
    center_x = (min_x + max_x) / 2.0
    center_z = (min_z + max_z) / 2.0

    def world_to_svg(x: float, z: float) -> Tuple[float, float]:
        sx = (svg_w / 2.0) + (x - center_x) * scale
        # Invert Z so +Z goes down
        sy = (svg_h / 2.0) + (z - center_z) * scale
        return sx, sy

    length_val = dimensions.get("length", width_units)
    width_val = dimensions.get("width", depth_units)
    floor_area = dimensions.get("floor_area", length_val * width_val * 0.65)
    unit_label = "m" if is_calibrated else "units"
    area_unit = "m²" if is_calibrated else "sq units"
    badge_color = "#10B981" if is_calibrated else "#F59E0B"
    badge_text = "Metric Calibrated (1:1)" if is_calibrated else "Arbitrary SfM Scale (Uncalibrated)"

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">',
        '  <defs>',
        '    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">',
        '      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#161E2E" stroke-width="1"/>',
        '    </pattern>',
        '  </defs>',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="#0A0D14"/>',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="url(#grid)"/>',
        '  <!-- Header / Metadata -->',
        '  <text x="50" y="55" fill="#F8FAFC" font-family="system-ui, sans-serif" font-size="24" font-weight="bold">SCANFORGE ARCHITECTURAL FLOOR PLAN</text>',
        f'  <text x="50" y="85" fill="#94A3B8" font-family="system-ui, sans-serif" font-size="14">Slice Height: Y = {y_slice:.2f} {unit_label} | Total Area: ~{floor_area:.2f} {area_unit}</text>',
        f'  <rect x="{svg_w - 320}" y="35" width="270" height="34" rx="6" fill="{badge_color}22" stroke="{badge_color}" stroke-width="1.5"/>',
        f'  <text x="{svg_w - 185}" y="57" fill="{badge_color}" font-family="system-ui, sans-serif" font-size="12" font-weight="600" text-anchor="middle">{badge_text}</text>',
        '  <!-- Wall Segments -->',
        '  <g stroke="#38BDF8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">',
    ]

    for seg in segments_2d:
        p0_x, p0_y = world_to_svg(seg[0, 0], seg[0, 1])
        p1_x, p1_y = world_to_svg(seg[1, 0], seg[1, 1])
        svg_lines.append(f'    <line x1="{p0_x:.1f}" y1="{p0_y:.1f}" x2="{p1_x:.1f}" y2="{p1_y:.1f}"/>')

    # Dimension callouts
    dim_y = svg_h - 60
    svg_lines.extend([
        '  </g>',
        '  <!-- Dimension Labels -->',
        f'  <g fill="#94A3B8" font-family="system-ui, sans-serif" font-size="13">',
        f'    <text x="50" y="{dim_y}" fill="#38BDF8">Length (X): {length_val:.2f} {unit_label}</text>',
        f'    <text x="250" y="{dim_y}" fill="#818CF8">Width (Z): {width_val:.2f} {unit_label}</text>',
        f'    <text x="450" y="{dim_y}" fill="#10B981">Area: {floor_area:.2f} {area_unit}</text>',
        '  </g>',
        '  <!-- Compass -->',
        f'  <g transform="translate({svg_w - 80}, {svg_h - 80})">',
        '    <circle r="24" fill="#161E2E" stroke="#334155" stroke-width="1.5"/>',
        '    <path d="M 0 -18 L 6 0 L 0 -4 L -6 0 Z" fill="#38BDF8"/>',
        '    <path d="M 0 18 L 6 0 L 0 4 L -6 0 Z" fill="#64748B"/>',
        '    <text x="0" y="-22" fill="#38BDF8" font-size="10" font-weight="bold" text-anchor="middle">N</text>',
        '  </g>',
        '</svg>'
    ])

    output_path.write_text("\n".join(svg_lines), encoding="utf-8")


def render_floor_plan_png(
    segments_2d: np.ndarray,
    bounds: Tuple[float, float, float, float],
    output_path: Path,
    dimensions: Dict[str, float],
    is_calibrated: bool,
    y_slice: float,
):
    """
    Renders high-resolution raster floor plan preview PNG.
    """
    min_x, max_x, min_z, max_z = bounds
    width_units = max(max_x - min_x, 0.1)
    depth_units = max(max_z - min_z, 0.1)

    img_w, img_h = 1600, 1200
    margin = 120
    draw_w = img_w - 2 * margin
    draw_h = img_h - 2 * margin

    scale = min(draw_w / width_units, draw_h / depth_units)
    center_x = (min_x + max_x) / 2.0
    center_z = (min_z + max_z) / 2.0

    def world_to_px(x: float, z: float) -> Tuple[int, int]:
        px = int(round((img_w / 2.0) + (x - center_x) * scale))
        py = int(round((img_h / 2.0) + (z - center_z) * scale))
        return px, py

    # Background
    img = Image.new("RGB", (img_w, img_h), color=(10, 13, 20))
    draw = ImageDraw.Draw(img)

    # Grid
    grid_spacing = 40
    for x in range(0, img_w, grid_spacing):
        draw.line([(x, 0), (x, img_h)], fill=(22, 30, 46), width=1)
    for y in range(0, img_h, grid_spacing):
        draw.line([(0, y), (img_w, y)], fill=(22, 30, 46), width=1)

    # Wall segments (thick cyan lines)
    for seg in segments_2d:
        p0 = world_to_px(seg[0, 0], seg[0, 1])
        p1 = world_to_px(seg[1, 0], seg[1, 1])
        draw.line([p0, p1], fill=(56, 189, 248), width=3)

    # Load default font
    font = ImageFont.load_default()

    # Titles & info
    unit_label = "m" if is_calibrated else "units"
    area_unit = "m²" if is_calibrated else "sq units"
    length_val = dimensions.get("length", width_units)
    width_val = dimensions.get("width", depth_units)
    floor_area = dimensions.get("floor_area", length_val * width_val * 0.65)

    draw.text((50, 45), "SCANFORGE ARCHITECTURAL FLOOR PLAN", fill=(248, 250, 252), font=font)
    draw.text((50, 75), f"Slice Height: Y = {y_slice:.2f} {unit_label} | Total Floor Area: ~{floor_area:.2f} {area_unit}", fill=(148, 163, 184), font=font)

    badge = "Metric Calibrated (1:1)" if is_calibrated else "Arbitrary SfM Scale"
    badge_col = (16, 185, 129) if is_calibrated else (245, 158, 11)
    draw.rectangle([(img_w - 280, 40), (img_w - 50, 75)], outline=badge_col, width=2)
    draw.text((img_w - 260, 50), badge, fill=badge_col, font=font)

    # Footer metrics
    draw.text((50, img_h - 60), f"Length: {length_val:.2f} {unit_label}  |  Width: {width_val:.2f} {unit_label}  |  Area: {floor_area:.2f} {area_unit}", fill=(56, 189, 248), font=font)

    img.save(str(output_path))


def update_floor_plan_scale(workdir: Path, new_scale: float, is_calibrated: bool):
    """
    Hook called by /api/jobs/{id}/calibrate to re-render floor_plan.svg and floor_plan.png
    with updated metric dimensions.
    """
    try:
        report_file = workdir / "quality_report.json"
        dimensions = {}
        if report_file.exists():
            data = json.loads(report_file.read_text())
            dims = data.get("dimensions_meters", {})
            dimensions = {
                "length": dims.get("length", 5.0) * new_scale,
                "width": dims.get("width", 4.0) * new_scale,
                "height": dims.get("height", 2.6) * new_scale,
                "floor_area": data.get("floor_area_sqm", 20.0) * (new_scale ** 2),
            }

        target_mesh = workdir / "mesh_calibrated.ply"
        if not target_mesh.exists():
            target_mesh = workdir / "mesh_aligned.ply"
        if not target_mesh.exists():
            target_mesh = workdir / "mesh_decimated.ply"

        if target_mesh.exists():
            y_slice = 1.10 * (new_scale if is_calibrated else 1.0)
            segments, bounds = slice_mesh_xz(target_mesh, y_slice)
            render_floor_plan_svg(segments, bounds, workdir / "floor_plan.svg", dimensions, is_calibrated, y_slice)
            render_floor_plan_png(segments, bounds, workdir / "floor_plan.png", dimensions, is_calibrated, y_slice)
            logger.info(f"[FloorPlan] Updated floor plan vector/raster outputs with scale {new_scale:.4f}.")
    except Exception as e:
        logger.warning(f"[FloorPlan] Could not update floor plan scale: {e}")


class FloorPlanStage(Stage):
    """
    Generates 2D floor plans (SVG vector + PNG raster) from the leveled 3D mesh.
    """
    name: str = "floor_plan"
    weight: float = 1.0
    declared_outputs: List[str] = ["floor_plan.svg", "floor_plan.png"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[FloorPlan] Generating architectural 2D floor plan...")

        # Locate leveled/aligned mesh
        target_mesh = ctx.workdir / "mesh_aligned.ply"
        if not target_mesh.exists():
            target_mesh = ctx.workdir / "mesh_decimated.ply"
        if not target_mesh.exists():
            target_mesh = ctx.workdir / "mesh_tsdf_raw.ply"
        if not target_mesh.exists():
            target_mesh = ctx.workdir / "mesh_cleaned.ply"

        if not target_mesh.exists():
            raise FileNotFoundError(f"[FloorPlan] Target mesh not found in {ctx.workdir}")

        # Read room analysis and quality report for height / eye level
        y_floor = 0.0
        y_ceiling = 2.6
        median_cam_y = 1.5

        analysis_file = ctx.workdir / "room_analysis.json"
        if analysis_file.exists():
            try:
                adata = json.loads(analysis_file.read_text())
                y_floor = float(adata.get("floor_level", 0.0))
                y_ceiling = float(adata.get("ceiling_level", 2.6))
            except Exception:
                pass

        cam_file = ctx.workdir / "cameras_aligned.json"
        if cam_file.exists():
            try:
                cdata = json.loads(cam_file.read_text())
                median_cam_y = float(cdata.get("median_camera_height", 1.5))
            except Exception:
                pass

        is_calibrated = bool(ctx.params.get("is_calibrated", False))
        cumulative_scale = getattr(ctx, "cumulative_scale", 1.0)

        y_slice = compute_slice_height(
            y_floor=y_floor,
            y_ceiling=y_ceiling,
            median_cam_y=median_cam_y,
            cumulative_scale=cumulative_scale,
            is_calibrated=is_calibrated,
        )

        ctx.log_cb(f"[FloorPlan] Slicing mesh at Y = {y_slice:.3f} (is_calibrated={is_calibrated})...")
        segments_2d, bounds = slice_mesh_xz(target_mesh, y_slice)
        ctx.log_cb(f"[FloorPlan] Extracted {len(segments_2d):,} 2D cross-section boundary segments.")

        # Read dimensions from quality report if available
        dimensions = {"length": bounds[1] - bounds[0], "width": bounds[3] - bounds[2]}
        report_file = ctx.workdir / "quality_report.json"
        if report_file.exists():
            try:
                rdata = json.loads(report_file.read_text())
                dims = rdata.get("dimensions_meters", {})
                dimensions["length"] = dims.get("length", dimensions["length"])
                dimensions["width"] = dims.get("width", dimensions["width"])
                dimensions["floor_area"] = rdata.get("floor_area_sqm", dimensions["length"] * dimensions["width"] * 0.65)
            except Exception:
                pass

        svg_out = ctx.workdir / "floor_plan.svg"
        png_out = ctx.workdir / "floor_plan.png"

        render_floor_plan_svg(segments_2d, bounds, svg_out, dimensions, is_calibrated, y_slice)
        render_floor_plan_png(segments_2d, bounds, png_out, dimensions, is_calibrated, y_slice)

        ctx.log_cb(f"[FloorPlan] Created {svg_out.name} ({svg_out.stat().st_size:,} bytes) and {png_out.name} ({png_out.stat().st_size:,} bytes).")

        return StageResult(
            success=True,
            output_files=[svg_out, png_out],
            metadata={
                "slice_height": round(y_slice, 3),
                "num_segments": len(segments_2d),
                "is_calibrated": is_calibrated,
            }
        )

