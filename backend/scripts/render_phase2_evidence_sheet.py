"""
ScanForge Phase 2 Evidence Sheet Generator
Renders 4 canonical views (Perspective 1, Perspective 2, Top Plan, Side Elevation)
for each stage in Phase 2:
1. Raw Delaunay Mesh
2. Cleaned Mesh (floater removal)
3. Repaired Mesh (normal-aware plane snapping + envelope pruning)
4. Decimated Mesh (quadric boundary-preserved simplification)
5. Textured Mesh (photographic UV atlas)
6. Poisson Surface A/B (Screened Poisson reconstruction)
Composites all views into a comprehensive comparison contact sheet under outputs/.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any
from PIL import Image, ImageDraw, ImageFont


def render_model_views(
    model_path: Path,
    output_dir: Path,
    blender_bin: str = "blender"
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).parent / "blender_render_script.py"

    cmd = [
        blender_bin,
        "-b",
        "-P", str(script_path),
        "--",
        str(model_path),
        str(output_dir),
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        print(f"[RenderEvidence] Warning: Blender rendering failed for {model_path.name}:\n{res.stdout[:500]}")
        return {}

    views = {}
    for name in ("persp1.png", "persp2.png", "top.png", "side.png"):
        p = output_dir / name
        if p.exists():
            views[name] = p
    return views


def build_phase2_sheet(
    workdir: Path,
    output_sheet_path: Path,
    clip_title: str,
    blender_bin: str = "blender"
) -> bool:
    workdir = Path(workdir).resolve()
    output_sheet_path = Path(output_sheet_path).resolve()
    output_sheet_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n[EvidenceSheet] Compiling Phase 2 evidence for '{clip_title}' from {workdir}...")

    # Determine files for each stage
    stages = [
        ("1. Raw Delaunay Mesh", ["raw_mesh.glb", "preview_mesh.glb", "scene_dense_mesh.ply"]),
        ("2. Cleaned Mesh (Floaters Pruned)", ["mesh_cleaned.ply"]),
        ("3. Repaired Mesh (Planes Snapped & Clipped)", ["mesh_repaired.ply"]),
        ("4. Decimated Mesh (Boundary-Preserved)", ["mesh_decimated.ply"]),
        ("5. Photographic UV Textured Mesh", ["preview_textured.glb", "scene_textured.glb"]),
        ("6. Poisson Surface A/B (Dense Cloud)", ["mesh_poisson.glb", "mesh_poisson.ply"]),
    ]

    rendered_rows = []
    tmp_root = Path("/tmp/phase2_renders") / workdir.name
    tmp_root.mkdir(parents=True, exist_ok=True)

    for stage_label, filenames in stages:
        target_path = None
        for fn in filenames:
            p = workdir / fn
            if p.exists() and p.stat().st_size > 0:
                target_path = p
                break

        if not target_path:
            print(f"  [Skip] No geometry found for stage '{stage_label}'")
            continue

        stage_tmp_dir = tmp_root / target_path.stem
        print(f"  [Render] {stage_label} ({target_path.name})...")
        views = render_model_views(target_path, stage_tmp_dir, blender_bin=blender_bin)
        if views:
            # Inspect vertex/face count if ply/glb
            detail_str = target_path.name
            try:
                import trimesh
                m = trimesh.load(str(target_path), process=False)
                if isinstance(m, trimesh.Trimesh):
                    detail_str = f"{len(m.vertices):,} verts | {len(m.faces):,} faces"
            except Exception:
                pass
            rendered_rows.append((stage_label, detail_str, views))

    if not rendered_rows:
        print("[EvidenceSheet] Error: No stages could be rendered.")
        return False

    # Composite into grid
    # Each view is 800x600. Scale down to 480x360 for clean composite.
    panel_w, panel_h = 440, 330
    row_header_h = 44
    col_header_h = 50
    title_bar_h = 80

    total_cols = 4
    total_rows = len(rendered_rows)

    grid_w = total_cols * panel_w + 30
    grid_h = title_bar_h + col_header_h + total_rows * (panel_h + row_header_h) + 20

    sheet = Image.new("RGB", (grid_w, grid_h), color=(15, 23, 42))  # Slate-900
    draw = ImageDraw.Draw(sheet)

    # Master Title Header
    draw.text((25, 20), f"ScanForge Milestone P2c Phase 2 — Interior Mesh Progression", fill=(248, 250, 252))
    draw.text((25, 46), f"Test Dataset: {clip_title} | Workdir: {workdir.name}", fill=(148, 163, 184))

    # Column Headers (The 4 Canonical Views)
    col_titles = [
        "View 1: Perspective Front (Iso)",
        "View 2: Perspective Back (Iso)",
        "View 3: Top-Down Plan (looking -Y)",
        "View 4: Side Elevation (looking -X)",
    ]
    for c, title in enumerate(col_titles):
        col_x = 15 + c * panel_w
        draw.text((col_x + 10, title_bar_h + 16), title, fill=(56, 189, 248))

    current_y = title_bar_h + col_header_h

    for stage_label, detail_str, views in rendered_rows:
        # Row Header
        draw.rectangle([(15, current_y), (grid_w - 15, current_y + row_header_h - 6)], fill=(30, 41, 59))
        draw.text((25, current_y + 10), stage_label, fill=(241, 245, 249))
        draw.text((grid_w - 320, current_y + 10), detail_str, fill=(203, 213, 225))
        current_y += row_header_h

        # Views in order
        view_names = ["persp1.png", "persp2.png", "top.png", "side.png"]
        for c, vname in enumerate(view_names):
            if vname in views:
                img = Image.open(views[vname]).resize((panel_w - 6, panel_h - 6), Image.Resampling.LANCZOS)
                col_x = 15 + c * panel_w
                sheet.paste(img, (col_x, current_y))

        current_y += panel_h + 8

    sheet.save(str(output_sheet_path), quality=92)
    print(f"[EvidenceSheet] SUCCESS: Saved composite sheet ({grid_w}x{grid_h}) to:")
    print(f"  --> {output_sheet_path}")

    # Clean temporary frame directories
    shutil.rmtree(tmp_root, ignore_errors=True)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 render_phase2_evidence_sheet.py <workdir> <output_sheet.png> [clip_title]")
        sys.exit(1)

    wdir = Path(sys.argv[1])
    out = Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else wdir.name
    build_phase2_sheet(wdir, out, title)

