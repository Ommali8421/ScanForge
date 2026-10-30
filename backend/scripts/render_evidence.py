#!/usr/bin/env python3
"""
ScanForge Visual Evidence Renderer
Invokes headless Blender 4.1 to render 4 canonical views, then composites them into a 2x2 grid.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def render_4views_composite(
    model_path: Path,
    output_composite_path: Path,
    title: str = "",
    blender_bin: str = "blender"
) -> bool:
    model_path = Path(model_path).resolve()
    output_composite_path = Path(output_composite_path).resolve()
    if not model_path.exists():
        raise FileNotFoundError(f"Model path {model_path} does not exist.")

    tmp_dir = Path("/tmp/blender_renders") / model_path.stem
    tmp_dir.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).parent / "blender_render_script.py"

    cmd = [
        blender_bin,
        "-b",
        "-P", str(script_path),
        "--",
        str(model_path),
        str(tmp_dir),
    ]

    print(f"[RenderEvidence] Invoking Blender: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        print(f"[RenderEvidence] Blender failed (code {res.returncode}):\n{res.stdout}")
        return False

    v1_path = tmp_dir / "persp1.png"
    v2_path = tmp_dir / "persp2.png"
    v3_path = tmp_dir / "top.png"
    v4_path = tmp_dir / "side.png"

    for p in (v1_path, v2_path, v3_path, v4_path):
        if not p.exists():
            print(f"[RenderEvidence] Missing rendered view: {p}")
            return False

    img1 = Image.open(v1_path)
    img2 = Image.open(v2_path)
    img3 = Image.open(v3_path)
    img4 = Image.open(v4_path)

    w, h = img1.size
    grid_w = w * 2
    grid_h = h * 2 + 70
    comp = Image.new("RGB", (grid_w, grid_h), color=(15, 23, 42))  # slate-900
    draw = ImageDraw.Draw(comp)

    # Header title
    display_title = title or model_path.stem
    draw.text((30, 22), f"ScanForge Visual Evidence — {display_title}", fill=(248, 250, 252))

    # Paste panels
    comp.paste(img1, (0, 70))
    comp.paste(img2, (w, 70))
    comp.paste(img3, (0, 70 + h))
    comp.paste(img4, (w, 70 + h))

    # View panel labels
    draw.text((20, 85), "Perspective View 1 (Isometric Front)", fill=(56, 189, 248))
    draw.text((w + 20, 85), "Perspective View 2 (Isometric Back)", fill=(56, 189, 248))
    draw.text((20, 85 + h), "Top-Down View (Orthographic Plan, looking down +Y)", fill=(56, 189, 248))
    draw.text((w + 20, 85 + h), "Side View (Orthographic Elevation)", fill=(56, 189, 248))

    output_composite_path.parent.mkdir(parents=True, exist_ok=True)
    comp.save(str(output_composite_path), quality=95)
    print(f"[RenderEvidence] Composite 4-view image successfully saved to {output_composite_path}")

    # Clean up temp frames
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 render_evidence.py <model_path> <output_composite.png> [title]")
        sys.exit(1)

    m_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    title_str = sys.argv[3] if len(sys.argv) > 3 else ""

    success = render_4views_composite(m_path, out_path, title_str)
    sys.exit(0 if success else 1)
