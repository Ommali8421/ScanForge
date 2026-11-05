#!/usr/bin/env python3
"""
ScanForge 3DGS Proof Renderer (CUDA gsplat rasterization)
Renders 4 high-resolution diagnostic proof views of a 3D Gaussian Splat model:
1. Interior Eye-Level Walkthrough (Camera A from trajectory)
2. Interior Eye-Level Walkthrough (Camera B from trajectory)
3. Elevated 3/4 Cutaway Overview (looking at centered room from elevated angle)
4. Floor Plan Top-Down (XZ Layout looking down from above)
"""

import sys
import math
import json
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from plyfile import PlyData


def make_w2c(eye, lookat, up=np.array([0.0, 1.0, 0.0])):
    """
    Constructs an OpenCV-convention World-to-Camera (W2C) 4x4 matrix.
    Convention:
    - X_cam points RIGHT
    - Y_cam points DOWN (top of image corresponds to -Y_cam)
    - Z_cam points FORWARD along optical axis (lookat - eye)
    """
    eye = np.array(eye, dtype=float)
    lookat = np.array(lookat, dtype=float)
    up = np.array(up, dtype=float)

    z_cam = lookat - eye
    z_len = np.linalg.norm(z_cam)
    if z_len < 1e-6:
        z_cam = np.array([0.0, 0.0, 1.0])
    else:
        z_cam = z_cam / z_len

    # Camera right X: Forward x Up = Right
    x_cam = np.cross(z_cam, up)
    if np.linalg.norm(x_cam) < 1e-6:
        x_cam = np.cross(z_cam, np.array([0.0, 0.0, 1.0]))
    x_cam = x_cam / np.linalg.norm(x_cam)

    # Camera down Y: Forward x Right = Down
    y_cam = np.cross(z_cam, x_cam)
    y_cam = y_cam / np.linalg.norm(y_cam)

    # R transforms world to camera: [X_cam; Y_cam; Z_cam]
    R = np.vstack([x_cam, y_cam, z_cam])
    t = -R @ eye

    w2c = np.eye(4, dtype=np.float32)
    w2c[:3, :3] = R
    w2c[:3, 3] = t
    return w2c


def parse_cameras(workdir: Path):
    """Parses camera poses, prioritizing centered cameras_aligned.json and real cameras.txt intrinsics."""
    from scipy.spatial.transform import Rotation as R

    sparse_dirs = [
        workdir / "aligned_sparse" / "0",
        workdir / "sparse" / "0",
        workdir / "nerfstudio_data" / "sparse" / "0",
        workdir / "sparse_txt",
    ]

    # Default to 1080p landscape
    fx, fy, cx, cy = 1150.0, 1150.0, 960.0, 540.0
    w_orig, h_orig = 1920, 1080

    # Search for cameras.txt
    for d in sparse_dirs:
        cam_file = d / "cameras.txt"
        if cam_file.exists():
            for line in cam_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 5:
                    w_orig = int(parts[2])
                    h_orig = int(parts[3])
                    model = parts[1].upper()
                    if model == "SIMPLE_RADIAL" and len(parts) >= 7:
                        f = float(parts[4])
                        fx = fy = f
                        cx = float(parts[5])
                        cy = float(parts[6])
                    elif model in {"PINHOLE", "OPENCV"} and len(parts) >= 8:
                        fx = float(parts[4])
                        fy = float(parts[5])
                        cx = float(parts[6])
                        cy = float(parts[7])
                    break
            break

    # Prioritize cameras_aligned.json
    cameras_json = workdir / "cameras_aligned.json"
    if not cameras_json.exists() and (workdir / "cleaned_splat.ply").exists():
        # Check parent or siblings
        for cand in [workdir.parent / "cameras_aligned.json", workdir / "cameras_aligned.json"]:
            if cand.exists():
                cameras_json = cand
                break

    if cameras_json.exists():
        try:
            data = json.loads(cameras_json.read_text())
            cams = []
            for c in data.get("cameras", []):
                pos = np.array(c["position"], dtype=float)
                fwd = np.array(c.get("forward", [0.0, 0.0, 1.0]), dtype=float)
                up_vec = np.array(c.get("up", [0.0, 1.0, 0.0]), dtype=float)
                lookat = pos + fwd
                w2c = make_w2c(pos, lookat, up=up_vec)
                cams.append({
                    "name": c.get("name", "cam"),
                    "w2c": w2c,
                    "center": pos,
                    "forward": fwd,
                })
            if cams:
                return cams, fx, fy, cx, cy, w_orig, h_orig
        except Exception as e:
            print(f"Notice: failed parsing cameras_aligned.json ({e}), trying COLMAP sparse...")

    target_sparse = None
    for d in sparse_dirs:
        if (d / "images.txt").exists():
            target_sparse = d
            break

    if not target_sparse:
        return [], fx, fy, cx, cy, w_orig, h_orig

    # Read images.txt for camera poses
    images_txt = target_sparse / "images.txt"
    cams = []
    lines = images_txt.read_text().splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 10 and any(parts[9].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
            qw, qx, qy, qz = map(float, parts[1:5])
            tx, ty, tz = map(float, parts[5:8])
            img_name = parts[9]
            r_mat = R.from_quat([qx, qy, qz, qw]).as_matrix()
            w2c = np.eye(4, dtype=np.float32)
            w2c[:3, :3] = r_mat
            w2c[:3, 3] = [tx, ty, tz]
            cams.append({
                "name": img_name,
                "w2c": w2c,
                "center": -r_mat.T @ np.array([tx, ty, tz])
            })

    return cams, fx, fy, cx, cy, w_orig, h_orig


def render_splat_views(ply_path: str, output_image_path: str):
    p_path = Path(ply_path)
    if not p_path.exists():
        raise FileNotFoundError(f"PLY file not found: {ply_path}")

    print(f"Loading 3DGS PLY: {ply_path}...")
    ply = PlyData.read(str(p_path))["vertex"]
    pts = np.column_stack([ply["x"], ply["y"], ply["z"]]).astype(np.float32)
    num_points = len(pts)

    p_min_rob = np.percentile(pts, 2, axis=0)
    p_max_rob = np.percentile(pts, 98, axis=0)
    center = (p_min_rob + p_max_rob) / 2.0
    span = p_max_rob - p_min_rob
    diag = float(np.linalg.norm(span))

    print(f"Gaussians: {num_points:,}")
    print(f"Bounds: X=[{p_min_rob[0]:.2f}, {p_max_rob[0]:.2f}], Y=[{p_min_rob[1]:.2f}, {p_max_rob[1]:.2f}], Z=[{p_min_rob[2]:.2f}, {p_max_rob[2]:.2f}]")
    print(f"Robust Center: [{center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f}], Span: [{span[0]:.2f}, {span[1]:.2f}, {span[2]:.2f}], Diag: {diag:.2f} units")

    # Discover workdir from PLY path
    workdir = p_path.parent
    if workdir.name in {"splat_export", "outputs"}:
        workdir = workdir.parent

    colmap_cams, orig_fx, orig_fy, orig_cx, orig_cy, w_orig, h_orig = parse_cameras(workdir)

    # Check CUDA and gsplat availability
    has_cuda_gsplat = False
    try:
        import torch
        import gsplat
        if torch.cuda.is_available():
            has_cuda_gsplat = True
    except Exception as e:
        print(f"CUDA/gsplat not available ({e}), falling back to CPU projection.")

    panel_w, panel_h = 1280, 960

    if has_cuda_gsplat:
        import torch
        import gsplat

        print("Initializing GPU tensors for gsplat.rasterization...")
        means = torch.tensor(pts, dtype=torch.float32, device="cuda")
        quats = torch.tensor(
            np.column_stack([ply["rot_0"], ply["rot_1"], ply["rot_2"], ply["rot_3"]]),
            dtype=torch.float32,
            device="cuda"
        )
        quats = torch.nn.functional.normalize(quats, p=2, dim=-1)

        s0 = np.exp(np.clip(np.asarray(ply["scale_0"]), -20.0, 5.0))
        s1 = np.exp(np.clip(np.asarray(ply["scale_1"]), -20.0, 5.0))
        s2 = np.exp(np.clip(np.asarray(ply["scale_2"]), -20.0, 5.0))
        scales = torch.tensor(np.column_stack([s0, s1, s2]), dtype=torch.float32, device="cuda")

        opacities_raw = np.asarray(ply["opacity"], dtype=np.float32)
        opacities = torch.tensor(1.0 / (1.0 + np.exp(-np.clip(opacities_raw, -20.0, 20.0))), dtype=torch.float32, device="cuda")

        C0 = 0.28209479177387814
        sh_0 = torch.tensor(np.column_stack([ply["f_dc_0"], ply["f_dc_1"], ply["f_dc_2"]]), dtype=torch.float32, device="cuda")
        colors = torch.clamp(0.5 + C0 * sh_0, 0.0, 1.0)

        # Helper to render single view with gsplat
        def render_gsplat(w2c_mat, fx_in=None, fy_in=None, cx_in=None, cy_in=None):
            sx = panel_w / float(w_orig)
            sy = panel_h / float(h_orig)
            fx = fx_in if fx_in is not None else (orig_fx * sx)
            fy = fy_in if fy_in is not None else (orig_fy * sy)
            cx = cx_in if cx_in is not None else (orig_cx * sx)
            cy = cy_in if cy_in is not None else (orig_cy * sy)

            K = torch.tensor([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]], dtype=torch.float32, device="cuda").unsqueeze(0)
            viewmats = torch.tensor(w2c_mat, dtype=torch.float32, device="cuda").unsqueeze(0)

            with torch.no_grad():
                out, _, _ = gsplat.rasterization(
                    means=means,
                    quats=quats,
                    scales=scales,
                    opacities=opacities,
                    colors=colors,
                    viewmats=viewmats,
                    Ks=K,
                    width=panel_w,
                    height=panel_h,
                    near_plane=0.01,
                    far_plane=1e6,
                    radius_clip=0.0,
                    eps2d=0.3,
                    rasterize_mode="antialiased",
                )
            img_np = (torch.clamp(out[0], 0.0, 1.0).cpu().numpy() * 255.0).astype(np.uint8)
            return Image.fromarray(img_np)

        # 1. Camera A (First-Frame Spawn Camera: Frame 1)
        print("Rendering View 1: First-Frame Spawn Camera (Frame 1)...")
        if colmap_cams:
            cam1 = colmap_cams[0]
            title1 = f"View 1: First-Frame Spawn Camera ({cam1['name']})"
            img1 = render_gsplat(cam1["w2c"])
        else:
            title1 = "View 1: Interior Eye-Level Walkthrough"
            eye1 = center + np.array([0.0, 0.5, -0.6 * span[2]])
            w2c1 = make_w2c(eye1, center + np.array([0.0, 0.0, 0.5 * span[2]]))
            img1 = render_gsplat(w2c1, fx_in=1000.0, fy_in=1000.0, cx_in=panel_w/2.0, cy_in=panel_h/2.0)

        # 2. Camera B (Interior Walkthrough View)
        print("Rendering View 2: Interior Walkthrough View...")
        if colmap_cams and len(colmap_cams) > 1:
            idx2 = min(int(len(colmap_cams) * 0.50), len(colmap_cams) - 1)
            cam2 = colmap_cams[idx2]
            title2 = f"View 2: Interior Walkthrough ({cam2['name']})"
            img2 = render_gsplat(cam2["w2c"])
        else:
            title2 = "View 2: Interior Reverse Walkthrough"
            eye2 = center + np.array([0.0, 0.5, 0.6 * span[2]])
            w2c2 = make_w2c(eye2, center - np.array([0.0, 0.0, 0.5 * span[2]]))
            img2 = render_gsplat(w2c2, fx_in=1000.0, fy_in=1000.0, cx_in=panel_w/2.0, cy_in=panel_h/2.0)

        # 3. Elevated 3/4 Cutaway Overview (Looking at centered origin)
        print("Rendering View 3: Elevated 3/4 Cutaway Overview...")
        target3 = np.array([0.0, span[1] * 0.35, 0.0])
        eye3 = target3 + np.array([-1.2 * max(span[0], 3.0), span[1] * 1.3 + 1.5, -1.2 * max(span[2], 3.0)])
        w2c3 = make_w2c(eye3, target3, up=np.array([0.0, 1.0, 0.0]))
        title3 = "View 3: Elevated 3/4 Cutaway Overview"
        f_ov = 1000.0
        img3 = render_gsplat(w2c3, fx_in=f_ov, fy_in=f_ov, cx_in=panel_w/2.0, cy_in=panel_h/2.0)

        # 4. Floor Plan Top-Down (XZ Layout looking down from above)
        print("Rendering View 4: Floor Plan Top-Down (XZ Layout)...")
        target4 = np.array([0.0, 0.0, 0.0])
        eye4 = np.array([0.0, max(span[0], span[2], 5.0) * 1.6, 0.0])
        w2c4 = make_w2c(eye4, target4, up=np.array([0.0, 0.0, -1.0]))
        title4 = "View 4: Floor Plan Top-Down (XZ Layout)"
        f_top = 900.0
        img4 = render_gsplat(w2c4, fx_in=f_top, fy_in=f_top, cx_in=panel_w/2.0, cy_in=panel_h/2.0)

    else:
        # Fallback to CPU projection for non-CUDA test environments
        print("Using CPU point projection fallback...")
        def render_cpu(eye, lookat, up):
            w2c = make_w2c(eye, lookat, up)
            R = w2c[:3, :3]
            t = w2c[:3, 3]
            cam_pts = (R @ pts.T).T + t
            valid = cam_pts[:, 2] > 0.1
            cx_p, cy_p, cz_p = cam_pts[valid, 0], cam_pts[valid, 1], cam_pts[valid, 2]
            f = 800.0
            px = np.clip(panel_w / 2.0 + (cx_p / cz_p) * f, 0, panel_w - 1).astype(int)
            py = np.clip(panel_h / 2.0 + (cy_p / cz_p) * f, 0, panel_h - 1).astype(int)
            canvas = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
            canvas[py, px] = [200, 200, 200]
            return Image.fromarray(canvas)

        title1 = "View 1: Interior View A"
        img1 = render_cpu(center + [0, 0.5, -5], center, [0, 1, 0])
        title2 = "View 2: Interior View B"
        img2 = render_cpu(center + [0, 0.5, 5], center, [0, 1, 0])
        title3 = "View 3: Elevated Overview"
        img3 = render_cpu(center + [-8, 8, -8], center, [0, 1, 0])
        title4 = "View 4: Floor Plan Top-Down"
        img4 = render_cpu(center + [0, 15, 0], center, [0, 0, -1])

    # Assemble 2x2 Composite Sheet (2560 x 1920)
    print("Assembling 2560x1920 4-panel proof sheet...")
    sheet = Image.new("RGB", (panel_w * 2, panel_h * 2 + 60), color=(15, 17, 23))
    sheet.paste(img1, (0, 0))
    sheet.paste(img2, (panel_w, 0))
    sheet.paste(img3, (0, panel_h))
    sheet.paste(img4, (panel_w, panel_h))

    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    # Draw titles on each panel
    panels = [
        (title1, 20, 20),
        (title2, panel_w + 20, 20),
        (title3, 20, panel_h + 20),
        (title4, panel_w + 20, panel_h + 20),
    ]
    for text, px, py in panels:
        draw.rectangle([px - 6, py - 4, px + len(text) * 8 + 12, py + 22], fill=(10, 14, 20))
        draw.text((px, py), text, fill=(56, 189, 248), font=font)

    # Info footer
    footer_text = (
        f"ScanForge 3DGS Verification | Model: {p_path.name} | Gaussians: {num_points:,} | "
        f"Bounds: X=[{p_min_rob[0]:.2f}, {p_max_rob[0]:.2f}], Y=[{p_min_rob[1]:.2f}, {p_max_rob[1]:.2f}], Z=[{p_min_rob[2]:.2f}, {p_max_rob[2]:.2f}] | "
        f"CUDA Rasterizer: {'gsplat 1.4.0' if has_cuda_gsplat else 'CPU Fallback'}"
    )
    draw.text((25, panel_h * 2 + 20), footer_text, fill=(148, 163, 184), font=font)

    out_p = Path(output_image_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(out_p), quality=95)
    print(f"Proof sheet saved to {output_image_path} ({out_p.stat().st_size:,} bytes).")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 render_splat_views.py <splat.ply> <output.png>")
        sys.exit(1)
    render_splat_views(sys.argv[1], sys.argv[2])
